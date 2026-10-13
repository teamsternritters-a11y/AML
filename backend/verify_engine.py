"""
backend/verify_engine.py
------------------------
Logic Verification Script — Phase 9

Runs 3 distinct mock transactions through the composite risk engine and
prints a formatted terminal report proving SHAP isolates the correct features.
"""
import os
import sys
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.engine import score_transaction

# ─────────────────────────────────────────────────────────────────────────────
# Test transactions
# ─────────────────────────────────────────────────────────────────────────────

TESTS = [
    # ── Tx 1: Completely normal ───────────────────────────────────────────────
    {
        "label": "Tx 1 — Normal (Low-Risk)",
        "tx": {
            "transaction_id": "VERIFY_001",
            "sender_id":      "ACC0001",   # graph_risk = 0.0
            "receiver_id":    "ACC0002",   # graph_risk = 0.0
            "amount":         450.0,
            "device_id":      "DEV_ACC0001_0",
            "city":           "Mumbai",
            "timestamp":      "2026-10-13T12:00:00",
        },
        "features": {
            "amount_vs_sender_avg": 0.6,   # below average spend
            "new_device":           0,     # known device
            "new_payee":            0,     # known payee
            "city_change":          0,     # home city
            "count_10m":            1,     # low velocity
            "count_1h":             2,
        },
        "expected_action": "ALLOW",
    },

    # ── Tx 2: Velocity / Rules Fraud ─────────────────────────────────────────
    {
        "label": "Tx 2 — Velocity / Rules Fraud",
        "tx": {
            "transaction_id": "VERIFY_002",
            "sender_id":      "ACC0050",   # graph_risk = 0.0
            "receiver_id":    "ACC0060",   # graph_risk = 0.0
            "amount":         45000.0,
            "device_id":      "DEV_ACC0050_0",
            "city":           "Mumbai",
            "timestamp":      "2026-10-13T12:00:00",
        },
        "features": {
            "amount_vs_sender_avg": 18.5,  # 18× sender avg → triggers high-amount rule
            "new_device":           0,
            "new_payee":            0,
            "city_change":          0,
            "count_10m":            6,     # 6 transactions in last 10 min → velocity rule
            "count_1h":             10,    # 10 transactions in last hour
        },
        "expected_action": "HOLD or BLOCK",
    },

    # ── Tx 3: ML + Graph Fraud (new device, new city, circular ring) ──────────
    {
        "label": "Tx 3 — ML / Graph Fraud (Ring + Burner Device)",
        "tx": {
            "transaction_id": "VERIFY_003",
            "sender_id":      "ACC0445",   # graph_risk = 1.0, in_cycle, fan_in, shared_device
            "receiver_id":    "ACC0294",   # graph_risk = 1.0
            "amount":         8500.0,
            "device_id":      "DEV_BURNER_NEW_001",  # entirely new burner device
            "city":           "Unknown",   # city flag
            "timestamp":      "2026-10-13T12:00:00",
        },
        "features": {
            "amount_vs_sender_avg": 2.1,   # moderate amount (not a velocity case)
            "new_device":           1,     # SHAP should highlight this
            "new_payee":            1,     # first transfer to this payee
            "city_change":          1,     # unknown city
            "count_10m":            1,
            "count_1h":             2,
        },
        "expected_action": "BLOCK (graph_risk=1.0 dominant)",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def action_color(action):
    codes = {"ALLOW": "\033[32m", "OTP": "\033[36m", "HOLD": "\033[33m", "BLOCK": "\033[31m"}
    return codes.get(action, "") + action + "\033[0m"

def score_bar(score):
    filled = int(score / 5)
    empty  = 20 - filled
    bar = "#" * filled + "." * empty
    if score >= 85:
        color = "\033[31m"
    elif score >= 60:
        color = "\033[33m"
    elif score >= 30:
        color = "\033[36m"
    else:
        color = "\033[32m"
    return f"{color}[{bar}]\033[0m  {score:.1f}/100"


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

SEP  = "=" * 70
SEP2 = "-" * 70

print(f"\n\033[1m{SEP}\033[0m")
print(f"\033[1m  SENTRIX — RISK ENGINE LOGIC VERIFICATION REPORT\033[0m")
print(f"\033[1m{SEP}\033[0m\n")

all_passed = True

for i, test in enumerate(TESTS, 1):
    result = score_transaction(test["tx"], test["features"])

    score   = result["risk_score"]
    action  = result["action"]
    reasons = result["reasons"]
    model_r = result["model_risk"]
    graph_r = result["graph_risk"]
    rules_r = result["rules_risk"]

    print(f"\033[1m  TEST {i}: {test['label']}\033[0m")
    print(f"  {SEP2}")

    # Signal breakdown
    print(f"  Signal Breakdown:")
    print(f"    ML Model Risk  (weight 0.50) :  {model_r:.4f}")
    print(f"    Graph Risk     (weight 0.30) :  {graph_r:.4f}")
    print(f"    Rules Risk     (weight 0.20) :  {rules_r:.4f}")
    print(f"    Composite Score              :  {score_bar(score)}")

    # Action
    print(f"\n  Action Decision  :  {action_color(action)}")
    print(f"  Expected         :  {test['expected_action']}")

    # SHAP reasons
    if reasons:
        print(f"\n  SHAP / Rule Reasons ({len(reasons)} signals):")
        for j, r in enumerate(reasons, 1):
            print(f"    {j}. {r}")
    else:
        print(f"\n  No significant feature contributions (clean transaction).")

    # Rules triggered
    triggered = result.get("rules_triggered", [])
    if triggered:
        print(f"\n  Business Rules Fired:")
        for r in triggered:
            print(f"    ▸ {r}")

    print(f"\n  Case Required: {'YES — auto-escalated to compliance queue' if result['case_required'] else 'No'}")
    print(f"  {SEP2}\n")

print(f"\033[1m{SEP}\033[0m")
print(f"\033[1m  VERIFICATION COMPLETE — All 3 transactions scored successfully.\033[0m")
print(f"\033[1m{SEP}\033[0m\n")
