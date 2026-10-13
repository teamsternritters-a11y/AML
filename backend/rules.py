import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

"""
backend/rules.py
----------------
Rule-based fraud detection baseline for the Real-Time Fraud & AML Risk Orchestration
prototype. Defines 6 deterministic rules and evaluates them on the chronological
final-30% test split produced by Phase 1 data.

No sklearn, no ML model — pure Python logic only.
"""

import json
from typing import Union

import pandas as pd

FRAUD_AMOUNT_THRESHOLD = 50000


# ----------------------------------------------------------------
# apply_rules
# ----------------------------------------------------------------
def apply_rules(row: Union[dict, "pd.Series"]) -> dict:
    """
    Evaluate all 6 binary fraud-detection rules on a single transaction row.

    Parameters
    ----------
    row : dict or pd.Series
        Must contain keys/fields: amount, amount_vs_sender_avg, count_10m,
        count_1h, new_device, city_change, new_payee.

    Returns
    -------
    dict with keys:
        - rules_triggered : list[str]  — ordered IDs of fired rules, e.g. ["R1", "R3"]
        - rules_risk      : float      — 0 → 1 score (min(fired/3, 1.0), 4 dp)
    """
    rules_triggered = []

    # R1: High absolute amount
    if float(row["amount"]) > FRAUD_AMOUNT_THRESHOLD:
        rules_triggered.append("R1")

    # R2: Amount unusually high vs sender's historical average
    if float(row["amount_vs_sender_avg"]) > 5.0:
        rules_triggered.append("R2")

    # R3: High velocity in 10-minute window
    if int(row["count_10m"]) >= 3:
        rules_triggered.append("R3")

    # R4: High velocity in 1-hour window
    if int(row["count_1h"]) >= 8:
        rules_triggered.append("R4")

    # R5: New device AND city change simultaneously (ATO signature)
    if int(row["new_device"]) == 1 and int(row["city_change"]) == 1:
        rules_triggered.append("R5")

    # R6: New payee AND large amount (mule / structuring signature)
    if int(row["new_payee"]) == 1 and float(row["amount"]) > 30000:
        rules_triggered.append("R6")

    rules_risk = round(min(len(rules_triggered) / 3.0, 1.0), 4)

    return {
        "rules_triggered": rules_triggered,
        "rules_risk": float(rules_risk),
    }


# ----------------------------------------------------------------
# evaluate_rules_baseline
# ----------------------------------------------------------------
def evaluate_rules_baseline(features_df: pd.DataFrame) -> dict:
    """
    Evaluate the rule-based baseline on the chronological final-30% test split.

    Parameters
    ----------
    features_df : pd.DataFrame
        Output of compute_features — must contain all 6 feature columns
        plus 'timestamp' and 'is_fraud'.

    Returns
    -------
    dict : metrics dict stored under key "rules_baseline" in
           backend/generated/metrics.json.
    """
    # --- Sort chronologically and take final 30% ---
    df = features_df.sort_values("timestamp", ascending=True).reset_index(drop=True)
    split_idx = int(0.70 * len(df))
    test_df = df.iloc[split_idx:].reset_index(drop=True)

    print(f"Rules baseline evaluated on last 30% (chronological test set): {len(test_df)} rows")

    # --- Apply rules row-by-row ---
    y_true = test_df["is_fraud"].astype(int).tolist()
    y_pred = []
    rules_results = []

    for _, row in test_df.iterrows():
        result = apply_rules(row)
        rules_results.append(result)
        y_pred.append(1 if len(result["rules_triggered"]) >= 1 else 0)

    # --- Confusion matrix components ---
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    precision      = round(tp / (tp + fp), 4)  if (tp + fp) > 0 else 0.0
    recall         = round(tp / (tp + fn), 4)  if (tp + fn) > 0 else 0.0
    fpr            = round(fp / (fp + tn), 4)  if (fp + tn) > 0 else 0.0
    flagged        = tp + fp
    total_positive = tp + fn
    fraud_prevalence = round(total_positive / len(test_df), 4)

    # --- Print formatted confusion matrix ---
    print("\n" + "=" * 56)
    print("  RULES BASELINE — CONFUSION MATRIX (test split, 30%)")
    print("=" * 56)
    print(f"  {'':20s}  Predicted 0    Predicted 1")
    print(f"  {'Actual 0 (Legit)':20s}  TN={tn:<10d}  FP={fp}")
    print(f"  {'Actual 1 (Fraud)':20s}  FN={fn:<10d}  TP={tp}")
    print("=" * 56)
    print(f"\n  Precision          : {precision:.4f}")
    print(f"  Recall (Sensitivity): {recall:.4f}")
    print(f"  False-Positive Rate : {fpr:.4f}")
    print(f"  Flagged (TP + FP)   : {flagged}")
    print(f"  Fraud Prevalence    : {fraud_prevalence:.4f} ({total_positive}/{len(test_df)})")
    print("=" * 56)

    metrics = {
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(precision),
        "recall": float(recall),
        "fpr": float(fpr),
        "flagged": int(flagged),
        "fraud_prevalence": float(fraud_prevalence),
        "test_row_count": int(len(test_df)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }

    # --- Load existing metrics.json or start fresh, update, save ---
    _gen_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(_gen_dir, exist_ok=True)
    metrics_path = os.path.join(_gen_dir, "metrics.json")

    if os.path.exists(metrics_path):
        with open(metrics_path, "r") as f:
            all_metrics = json.load(f)
    else:
        all_metrics = {}

    all_metrics["rules_baseline"] = metrics

    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"\n  Metrics written to: {metrics_path}")

    return metrics


# ----------------------------------------------------------------
# __main__ block
# ----------------------------------------------------------------
if __name__ == "__main__":
    from backend.features import compute_features

    _DIR = os.path.dirname(__file__)
    _GEN = os.path.join(_DIR, "generated")

    print("Loading data...")
    transactions_df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    accounts_df     = pd.read_csv(os.path.join(_GEN, "accounts.csv"))
    print(f"Transactions loaded: {len(transactions_df):,} rows")

    print("\nComputing features...")
    features_df = compute_features(transactions_df, accounts_df)
    print(f"Features computed. Shape: {features_df.shape}")

    print("\nEvaluating rules baseline...")
    metrics = evaluate_rules_baseline(features_df)
