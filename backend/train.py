import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
import joblib
from sklearn.metrics import f1_score, confusion_matrix
from backend.features import compute_features, get_feature_columns
from backend.rules import evaluate_rules_baseline

"""
backend/train.py
----------------
LightGBM fraud model training with chronological splits, threshold optimisation,
SHAP explanations, and artifact persistence for the AML Risk Orchestration prototype.

Steps:
  1. Load & feature-engineer
  2. Chronological split (70% train / 30% test)
  3. Inner val split from train (85% / 15%)
  4. Train LightGBM with early stopping (LightGBM 4.x callbacks API)
  5. Threshold selection on val_df (maximise F1)
  6. Evaluate hybrid on test_df, append metrics.json
  7. SHAP explanations on test_df
  8. Save fraud_model.joblib, model_metadata.json, test_features.parquet
"""

# ---------------------------------------------------------------------------
# Helper: pretty side-by-side comparison printer
# ---------------------------------------------------------------------------
def _print_comparison(rules: dict, ml: dict) -> None:
    header = f"{'Metric':<22} {'Rules Baseline':>16} {'ML Model':>16}"
    sep    = "-" * len(header)
    print("\n" + sep)
    print("  MODEL COMPARISON — Chronological 30% Test Split")
    print(sep)
    print(f"  {header}")
    print(sep)
    metrics_order = [
        ("Precision",   "precision"),
        ("Recall",      "recall"),
        ("FPR",         "fpr"),
        ("TP",          "tp"),
        ("FP",          "fp"),
        ("TN",          "tn"),
        ("FN",          "fn"),
    ]
    for label, key in metrics_order:
        r_val = rules.get(key, "n/a")
        m_val = ml.get(key, "n/a")
        if isinstance(r_val, float):
            r_str = f"{r_val:.4f}"
        else:
            r_str = str(r_val)
        if isinstance(m_val, float):
            m_str = f"{m_val:.4f}"
        else:
            m_str = str(m_val)
        print(f"  {label:<22} {r_str:>16} {m_str:>16}")
    print(sep)
    print(f"  {'Threshold':<22} {'N/A':>16} {ml.get('threshold', 0):.4f}{'':>10}")
    print(sep + "\n")


def main() -> None:
    _DIR = os.path.dirname(__file__)
    _GEN = os.path.join(_DIR, "generated")
    _MDL = os.path.join(_DIR, "models")
    os.makedirs(_GEN, exist_ok=True)
    os.makedirs(_MDL, exist_ok=True)

    # -----------------------------------------------------------------------
    # Step 1: Load and prepare
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("STEP 1 — Load & Feature Engineering")
    print("=" * 60)

    transactions_df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    accounts_df     = pd.read_csv(os.path.join(_GEN, "accounts.csv"))
    print(f"Transactions loaded: {len(transactions_df):,} rows")

    features_df = compute_features(transactions_df, accounts_df)
    # Ensure ascending chronological order (compute_features already sorts, but be explicit)
    features_df = features_df.sort_values("timestamp", ascending=True).reset_index(drop=True)

    feature_cols = get_feature_columns()  # ["amount_vs_sender_avg", "new_device", "new_payee",
                                          #  "city_change", "count_10m", "count_1h"]

    # Fill NaN values with 0 — handles edge cases where prior history is missing
    features_df[feature_cols] = features_df[feature_cols].fillna(0)

    print(f"Features computed. Shape: {features_df.shape}")
    print(f"Feature columns: {feature_cols}")

    # -----------------------------------------------------------------------
    # Step 2: Chronological Split — 70% train / 30% test
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 2 — Chronological Split (70/30)")
    print("=" * 60)

    train_end_idx  = int(0.70 * len(features_df))
    train_full_df  = features_df.iloc[:train_end_idx].copy()
    test_df        = features_df.iloc[train_end_idx:].copy()

    train_fraud_pct = train_full_df["is_fraud"].mean() * 100
    test_fraud_pct  = test_df["is_fraud"].mean() * 100

    print(f"Train (70%) : {len(train_full_df):>6,} rows  |  fraud: {train_full_df['is_fraud'].sum():>5} ({train_fraud_pct:.2f}%)")
    print(f"Test  (30%) : {len(test_df):>6,} rows  |  fraud: {test_df['is_fraud'].sum():>5} ({test_fraud_pct:.2f}%)")
    print("NOTE: test_df rows will NEVER be used during training or threshold selection.")

    # -----------------------------------------------------------------------
    # Step 3: Inner validation split from train_full_df only (85% / 15%)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 3 — Inner Train/Val Split (85/15 within train)")
    print("=" * 60)

    val_start_idx = int(0.85 * len(train_full_df))
    train_df      = train_full_df.iloc[:val_start_idx].copy()
    val_df        = train_full_df.iloc[val_start_idx:].copy()

    print(f"Inner train : {len(train_df):>6,} rows  |  fraud: {train_df['is_fraud'].sum():>5}")
    print(f"Inner val   : {len(val_df):>6,} rows  |  fraud: {val_df['is_fraud'].sum():>5}")

    # -----------------------------------------------------------------------
    # Step 4: Train LightGBM
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 4 — LightGBM Training")
    print("=" * 60)

    neg_count = int((train_df["is_fraud"] == 0).sum())
    pos_count = int((train_df["is_fraud"] == 1).sum())
    print(f"Class distribution: neg={neg_count:,}, pos={pos_count:,}  (ratio {neg_count/max(pos_count,1):.1f}:1)")

    # Hyperparameter rationale:
    # - is_unbalance=True: lets LightGBM auto-weight classes; more stable than
    #   large scale_pos_weight which causes extreme leaf purity → early convergence.
    # - min_child_samples=5: allow splits on minority-class leaves (default 20 is
    #   too large for ~1k positive samples and causes 'no positive gain' at round 1).
    # - min_split_gain=0.0: don't prune splits on the first pass.
    # - num_leaves=15, max_depth=4: shallower trees find more unique split boundaries
    #   across 300 rounds instead of exhausting in 1.
    # - verbose=-1: suppress per-round LightGBM Info logs.
    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=15,
        max_depth=4,
        min_child_samples=5,
        min_split_gain=0.0,
        is_unbalance=True,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )

    X_train = train_df[feature_cols]
    y_train = train_df["is_fraud"]
    X_val   = val_df[feature_cols]
    y_val   = val_df["is_fraud"]

    # Train without early stopping — with only 6 features and extreme class imbalance,
    # binary_logloss on the validation set plateaus at round 1, causing early stopping to
    # terminate immediately. Running all 300 rounds gives the boosting ensemble enough trees
    # to refine probability estimates across the feature space.
    model.fit(X_train, y_train)
    print(f"Training complete. Estimators trained: {model.n_estimators_}")

    # -----------------------------------------------------------------------
    # Step 5: Threshold Selection on val_df (maximise F1, thresholds 0.1→0.9)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 5 — Threshold Selection (Val F1 Maximisation)")
    print("=" * 60)

    val_probs = model.predict_proba(X_val)[:, 1]

    best_threshold = 0.5
    best_val_f1    = -1.0

    thresholds = np.arange(0.10, 0.91, 0.05)
    for thr in thresholds:
        preds = (val_probs >= thr).astype(int)
        f1    = f1_score(y_val, preds, zero_division=0)
        if f1 > best_val_f1:
            best_val_f1    = f1
            best_threshold = thr

    best_threshold = float(round(best_threshold, 4))
    best_val_f1    = float(round(best_val_f1, 4))
    print(f"Chosen threshold : {best_threshold:.4f}")
    print(f"Val F1           : {best_val_f1:.4f}")

    # -----------------------------------------------------------------------
    # Step 6: Evaluate on test_df; update metrics.json
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 6 — Test Set Evaluation")
    print("=" * 60)

    X_test    = test_df[feature_cols]
    y_test    = test_df["is_fraud"].astype(int)
    test_probs = model.predict_proba(X_test)[:, 1]
    test_preds = (test_probs >= best_threshold).astype(int)

    cm = confusion_matrix(y_test, test_preds)
    tn, fp, fn, tp = cm.ravel()

    precision = round(float(tp / (tp + fp)), 4) if (tp + fp) > 0 else 0.0
    recall    = round(float(tp / (tp + fn)), 4) if (tp + fn) > 0 else 0.0
    fpr_val   = round(float(fp / (fp + tn)), 4) if (fp + tn) > 0 else 0.0

    print(f"  TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    print(f"  Precision : {precision:.4f}")
    print(f"  Recall    : {recall:.4f}")
    print(f"  FPR       : {fpr_val:.4f}")

    ml_metrics = {
        "tp":        int(tp),
        "fp":        int(fp),
        "tn":        int(tn),
        "fn":        int(fn),
        "precision": float(precision),
        "recall":    float(recall),
        "fpr":       float(fpr_val),
        "threshold": float(best_threshold),
    }

    # Ensure rules_baseline exists in metrics.json; create if missing
    metrics_path = os.path.join(_GEN, "metrics.json")
    if not os.path.exists(metrics_path):
        print("metrics.json not found — running rules baseline to create it...")
        evaluate_rules_baseline(features_df)

    with open(metrics_path, "r") as f:
        all_metrics = json.load(f)

    all_metrics["ml_model"] = ml_metrics

    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"\n  metrics.json updated at: {metrics_path}")

    # Side-by-side comparison
    _print_comparison(all_metrics.get("rules_baseline", {}), ml_metrics)

    # -----------------------------------------------------------------------
    # Step 7: SHAP Explanations on test_df
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("STEP 7 — SHAP Explanations")
    print("=" * 60)

    explainer   = shap.TreeExplainer(model)
    shap_raw    = explainer.shap_values(X_test)

    # Normalise SHAP output — works for list, 2D, and 3D formats
    if isinstance(shap_raw, list):
        # Older SHAP returns [neg_class_vals, pos_class_vals]
        shap_values = shap_raw[1]
    elif len(np.array(shap_raw).shape) == 3:
        # 3D: (samples, features, classes) — take positive class slice
        shap_values = np.array(shap_raw)[:, :, 1]
    else:
        # 2D: (samples, features) — binary model already collapsed
        shap_values = np.array(shap_raw)

    print(f"SHAP values shape: {shap_values.shape}")

    # Attach SHAP columns to test_df
    test_df = test_df.copy()
    for j, col in enumerate(feature_cols):
        test_df[f"shap_{col}"] = shap_values[:, j]

    # Print mean absolute SHAP per feature (global importance)
    print("\n  Global Feature Importance (mean |SHAP|):")
    mean_shap = np.abs(shap_values).mean(axis=0)
    for col, importance in sorted(zip(feature_cols, mean_shap), key=lambda x: -x[1]):
        print(f"    {col:<25} : {importance:.5f}")

    # -----------------------------------------------------------------------
    # Step 8: Save Artifacts
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 8 — Saving Artifacts")
    print("=" * 60)

    # 8a. Trained model
    model_path = os.path.join(_MDL, "fraud_model.joblib")
    joblib.dump(model, model_path)
    print(f"  Model saved       : {model_path}")

    # 8b. Model metadata JSON
    model_metadata = {
        "feature_cols": feature_cols,
        "threshold":    float(best_threshold),
        "val_f1":       float(best_val_f1),
        "train_size":   int(len(train_full_df)),
        "test_size":    int(len(test_df)),
    }
    metadata_path = os.path.join(_MDL, "model_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(model_metadata, f, indent=2)
    print(f"  Metadata saved    : {metadata_path}")

    # 8c. test_features.parquet — contains all test rows with features + SHAP columns
    parquet_path = os.path.join(_GEN, "test_features.parquet")
    test_df.to_parquet(parquet_path, index=False)
    print(f"  test_features.parquet saved : {parquet_path}")
    print(f"    Columns: {list(test_df.columns)}")
    print(f"    Rows   : {len(test_df):,}")

    print("\n" + "=" * 60)
    print("Training complete. Model and artifacts saved.")
    print("=" * 60)


if __name__ == "__main__":
    main()
