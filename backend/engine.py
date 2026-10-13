import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""
backend/engine.py
-----------------
Real-Time Risk Orchestration Engine for the AML / Fraud prototype.

Merges three risk signals into a single composite score per transaction:
  1. ML model probability  (LightGBM, weight=0.50)
  2. Graph risk            (NetworkX graph analysis, weight=0.30)
  3. Rule-based risk       (deterministic rules, weight=0.20)

Artifacts are loaded ONCE at module import time so per-request latency
stays well under 100 ms.
"""

import json
import time
import warnings

# Suppress harmless sklearn feature-name warning (model fitted with DataFrame,
# predicted with ndarray) and SHAP binary-classifier output-format notice.
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="LightGBM binary classifier with TreeExplainer",
    category=UserWarning,
)

import joblib
import shap
import numpy as np
import pandas as pd

from backend.rules import apply_rules
from backend.features import get_feature_columns

# ---------------------------------------------------------------------------
# Global state — loaded LAZILY on first scoring call
# (allows the module to import cleanly on a fresh Render deploy where
#  the build command hasn't run yet)
# ---------------------------------------------------------------------------

_DIR = os.path.dirname(__file__)

MODEL = None
METADATA = None
GRAPH_RISKS = None
EXPLAINER = None
FEATURE_COLS = get_feature_columns()

_artifacts_loaded = False


def _load_artifacts():
    """Load ML model, graph risks, and SHAP explainer once on first use."""
    global MODEL, METADATA, GRAPH_RISKS, EXPLAINER, _artifacts_loaded
    if _artifacts_loaded:
        return
    print('[engine] Loading artifacts...')
    MODEL = joblib.load(os.path.join(_DIR, 'models', 'fraud_model.joblib'))
    METADATA = json.load(open(os.path.join(_DIR, 'models', 'model_metadata.json')))
    GRAPH_RISKS = json.load(open(os.path.join(_DIR, 'generated', 'graph_risks.json')))
    EXPLAINER = shap.TreeExplainer(MODEL)
    _artifacts_loaded = True
    print('[engine] Artifacts loaded.')

ACTION_THRESHOLDS = {'ALLOW': 30, 'OTP': 60, 'HOLD': 85, 'BLOCK': 100}

_FEATURE_TEMPLATES = {
    'amount_vs_sender_avg': lambda val: f'Amount is {val:.1f}x sender previous average',
    'new_device':           lambda val: 'New device for this sender',
    'new_payee':            lambda val: 'First transfer to this receiver',
    'city_change':          lambda val: 'City differs from sender usual location',
    'count_10m':            lambda val: f'{val:.0f} transactions in the last 10 minutes',
    'count_1h':             lambda val: f'{val:.0f} transactions in the last hour',
}

_BINARY_FEATURES = {'new_device', 'new_payee', 'city_change'}


def score_transaction(tx: dict, historical_features: dict) -> dict:
    _load_artifacts()
    feature_vector = [float(historical_features.get(col, 0.0)) for col in FEATURE_COLS]
    # Wrap as DataFrame so LGBMClassifier doesn't warn about missing feature names
    fv_df  = pd.DataFrame([feature_vector], columns=FEATURE_COLS)
    fv_arr = fv_df.values                             # shape (1, n_features)
    prob = MODEL.predict_proba(fv_df)[0][1]
    model_risk = float(prob)

    sender_id   = str(tx.get('sender_id', ''))
    receiver_id = str(tx.get('receiver_id', ''))
    sender_graph   = GRAPH_RISKS.get(sender_id,   {})
    receiver_graph = GRAPH_RISKS.get(receiver_id, {})
    graph_risk = max(
        float(sender_graph.get('graph_risk',   0.0)),
        float(receiver_graph.get('graph_risk', 0.0)),
    )

    combined_data   = {**tx, **historical_features}
    rules_out       = apply_rules(combined_data)
    rules_risk      = float(rules_out['rules_risk'])
    rules_triggered = rules_out['rules_triggered']

    raw        = 0.5 * model_risk + 0.3 * graph_risk + 0.2 * rules_risk
    risk_score = round(raw * 100, 1)

    if risk_score < ACTION_THRESHOLDS['ALLOW']:
        action = 'ALLOW'
    elif risk_score < ACTION_THRESHOLDS['OTP']:
        action = 'OTP'
    elif risk_score < ACTION_THRESHOLDS['HOLD']:
        action = 'HOLD'
    else:
        action = 'BLOCK'

    # fv_arr already defined as np.array shape (1, n_features)
    shap_values = EXPLAINER.shap_values(fv_arr)
    # SHAP binary classifier can return:
    #   list of 2 arrays   -> [neg_class_arr, pos_class_arr], each shape (1, n_features)
    #   3-D ndarray        -> shape (1, n_features, 2)
    #   2-D ndarray        -> shape (1, n_features)  (single output)
    if isinstance(shap_values, list):
        # Newer SHAP: list[ndarray]  — pick positive class (index 1)
        sv = np.array(shap_values[1])[0]
    else:
        sv_arr = np.array(shap_values)
        if sv_arr.ndim == 3:
            # shape (1, n_features, 2)
            sv = sv_arr[0, :, 1]
        else:
            # shape (1, n_features)
            sv = sv_arr[0]

    ml_reasons = []
    for feat_name, shap_val, feat_val in zip(FEATURE_COLS, sv, feature_vector):
        if float(shap_val) <= 0.01:
            continue
        if feat_name in _BINARY_FEATURES and float(feat_val) <= 0:
            continue
        template = _FEATURE_TEMPLATES.get(feat_name)
        if template is None:
            continue
        ml_reasons.append((float(shap_val), template(float(feat_val))))

    ml_reasons.sort(key=lambda x: -x[0])
    reasons = [r for _, r in ml_reasons]

    if graph_risk > 0.3:
        dominant_graph = (
            sender_graph
            if sender_graph.get('graph_risk', 0) >= receiver_graph.get('graph_risk', 0)
            else receiver_graph
        )
        if dominant_graph.get('in_cycle', False):
            reasons.append('Account involved in circular transfer pattern')
        if dominant_graph.get('fan_in_flag', False):
            reasons.append('Multiple senders funding this account')
        if dominant_graph.get('shared_device_flag', False):
            reasons.append('Device shared with another account')

    reasons = reasons[:3]

    return {
        'transaction_id':         tx.get('transaction_id', 'TEST'),
        'risk_score':             float(risk_score),
        'action':                 action,
        'model_risk':             float(model_risk),
        'graph_risk':             float(graph_risk),
        'rules_risk':             float(rules_risk),
        'rules_triggered':        rules_triggered,
        'reasons':                reasons,
        'case_required':          action == 'BLOCK',
        'sender_graph_signals':   sender_graph,
        'receiver_graph_signals': receiver_graph,
    }


if __name__ == '__main__':
    print('=' * 60)
    print('ENGINE SMOKE TEST - Phase 5')
    print('=' * 60)
    print(f'\nModel loaded  : {type(MODEL).__name__}, n_estimators={MODEL.n_estimators_}')
    print(f'Graph nodes   : {len(GRAPH_RISKS):,} accounts in GRAPH_RISKS')
    print(f'Feature cols  : {FEATURE_COLS}')

    tx = {
        'transaction_id': 'TX_TEST_001',
        'sender_id':      'ACC0996',
        'receiver_id':    'ACC1193',
        'amount':         75000.0,
        'device_id':      'DEV_SHARED_00',
        'city':           'Mumbai',
        'timestamp':      '2024-12-31T23:59:00',
    }
    historical_features = {
        'amount_vs_sender_avg': 12.5,
        'new_device':           1,
        'new_payee':            1,
        'city_change':          1,
        'count_10m':            4,
        'count_1h':             9,
    }

    start_time = time.perf_counter()
    result = score_transaction(tx, historical_features)
    latency = (time.perf_counter() - start_time) * 1000

    print('\n--- Result ---')
    print(json.dumps(result, indent=2, default=str))
    print(f'\n--- Latency: {latency:.2f} ms ---')

    assert latency < 100, f'FAIL: Latency {latency:.2f} ms exceeded 100 ms cap'
    assert 0 <= result['risk_score'] <= 100, f'FAIL: risk_score out of [0, 100]'

    print('\n' + '=' * 60)
    print('Engine check passed.')
    print('=' * 60)
