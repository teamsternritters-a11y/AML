import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import time
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.engine import score_transaction
from backend.features import get_feature_columns
from backend.graph import build_graph, get_neighborhood, get_account_graph_risk

app = FastAPI(title="AML Risk Orchestration API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

CASES = {}
SCORED_TRANSACTIONS = []
G = None
HISTORY_DF = None
SENDER_HISTORY_DICT = {}
GRAPH_RISKS = {}
START_TIME = time.time()
FEATURE_COLS = get_feature_columns()

_DIR = os.path.dirname(__file__)
_GEN = os.path.join(_DIR, "generated")
_10MIN_S = 600
_1H_S = 3600

@app.on_event("startup")
async def _startup():
    global G, HISTORY_DF, SENDER_HISTORY_DICT, GRAPH_RISKS
    print("[API] Loading transaction history...")
    tx_df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    tx_df["_ts_dt"] = pd.to_datetime(tx_df["timestamp"])
    tx_df = tx_df.sort_values("_ts_dt", ascending=True).reset_index(drop=True)
    HISTORY_DF = tx_df
    print("[API] Loading graph risks...")
    with open(os.path.join(_GEN, "graph_risks.json")) as f:
        GRAPH_RISKS = json.load(f)
    print("[API] Building transaction graph (30-day rolling window)...")
    G = build_graph(tx_df, max_days=30)
    for acc_id, risk_dict in GRAPH_RISKS.items():
        if G.has_node(acc_id):
            G.nodes[acc_id]["graph_risk"] = risk_dict.get("graph_risk", 0.0)
    print("[API] Building sender history index...")
    for sender_id, grp in tx_df.groupby("sender_id"):
        rows = []
        for _, row in grp.iterrows():
            rows.append({
                "timestamp":   row["timestamp"],
                "_ts_epoch":   int(row["_ts_dt"].timestamp()),
                "amount":      float(row["amount"]),
                "device_id":   str(row["device_id"]),
                "receiver_id": str(row["receiver_id"]),
                "city":        str(row["city"]),
            })
        SENDER_HISTORY_DICT[str(sender_id)] = rows
    print(f"[API] Ready. Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

def _compute_inline_features(sender_id, receiver_id, amount, device_id, city, ts_epoch):
    prior_rows = [r for r in SENDER_HISTORY_DICT.get(sender_id, []) if r["_ts_epoch"] < ts_epoch]
    if prior_rows:
        prior_mean = sum(r["amount"] for r in prior_rows) / len(prior_rows)
        amount_vs_sender_avg = round(amount / prior_mean, 6) if prior_mean != 0 else 1.0
    else:
        amount_vs_sender_avg = 1.0
    past_devices = {r["device_id"] for r in prior_rows}
    new_device = 0 if device_id in past_devices else 1
    past_payees = {r["receiver_id"] for r in prior_rows}
    new_payee = 0 if receiver_id in past_payees else 1
    city_change = 0
    if prior_rows:
        city_counts = {}
        for r in prior_rows:
            city_counts[r["city"]] = city_counts.get(r["city"], 0) + 1
        max_cnt = max(city_counts.values())
        modes = [c for c, v in city_counts.items() if v == max_cnt]
        if len(modes) == 1:
            city_change = 0 if city == modes[0] else 1
    cutoff_10m = ts_epoch - _10MIN_S
    cutoff_1h  = ts_epoch - _1H_S
    count_10m = sum(1 for r in prior_rows if r["_ts_epoch"] >= cutoff_10m)
    count_1h  = sum(1 for r in prior_rows if r["_ts_epoch"] >= cutoff_1h)
    return {"amount_vs_sender_avg": amount_vs_sender_avg, "new_device": new_device,
            "new_payee": new_payee, "city_change": city_change, "count_10m": count_10m, "count_1h": count_1h}

class ScoreRequest(BaseModel):
    transaction_id: str = "LIVE_TX"
    sender_id: str
    receiver_id: str
    amount: float
    device_id: str = ""
    city: str = ""
    timestamp: str = ""

class DecisionRequest(BaseModel):
    decision: str
    note: str = ""

@app.post("/score")
async def score(req: ScoreRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be > 0")
    if not req.sender_id.strip():
        raise HTTPException(status_code=422, detail="sender_id must be non-empty")
    if not req.receiver_id.strip():
        raise HTTPException(status_code=422, detail="receiver_id must be non-empty")
    try:
        ts_dt = pd.to_datetime(req.timestamp)
        ts_epoch = int(ts_dt.timestamp())
    except Exception:
        ts_dt = datetime.now(timezone.utc)
        ts_epoch = int(ts_dt.timestamp())
    tx = {"transaction_id": req.transaction_id, "sender_id": req.sender_id,
          "receiver_id": req.receiver_id, "amount": req.amount,
          "device_id": req.device_id, "city": req.city, "timestamp": req.timestamp}
    historical_features = _compute_inline_features(
        req.sender_id, req.receiver_id, req.amount, req.device_id, req.city, ts_epoch)
    result = score_transaction(tx, historical_features)
    result.update({
        "sender_id": req.sender_id,
        "receiver_id": req.receiver_id,
        "amount": req.amount,
        "device_id": req.device_id,
        "city": req.city,
        "timestamp": req.timestamp or ts_dt.isoformat()
    })
    SCORED_TRANSACTIONS.insert(0, result)
    if len(SCORED_TRANSACTIONS) > 1000:
        SCORED_TRANSACTIONS.pop()
    if result.get("case_required", False):
        case_id = f"CASE{len(CASES) + 1:05d}"
        case = {"case_id": case_id, "transaction_id": result["transaction_id"],
                "sender_id": req.sender_id, "risk_score": result["risk_score"],
                "action": result["action"], "reasons": result["reasons"],
                "sender_graph_signals": result["sender_graph_signals"],
                "receiver_graph_signals": result["receiver_graph_signals"],
                "status": "open", "created_at": datetime.now(timezone.utc).isoformat(),
                "reviewed_at": None, "reviewer_decision": None, "reviewer_note": None}
        CASES[case_id] = case
        result["case_id"] = case_id
    return result

@app.get("/transactions")
async def get_transactions(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None), min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None)):
    filtered = SCORED_TRANSACTIONS
    if action:
        filtered = [t for t in filtered if t.get("action") == action.upper()]
    if min_score is not None:
        filtered = [t for t in filtered if t.get("risk_score", 0) >= min_score]
    if max_score is not None:
        filtered = [t for t in filtered if t.get("risk_score", 0) <= max_score]
    return {"items": filtered[offset:offset + limit], "total_count": len(filtered)}

@app.get("/cases")
async def get_cases(status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    cases_list = list(CASES.values())
    if status:
        cases_list = [c for c in cases_list if c.get("status") == status]
    cases_list = sorted(cases_list, key=lambda c: c.get("created_at", ""), reverse=True)
    return {"items": cases_list[offset:offset + limit], "total_count": len(cases_list)}

@app.post("/cases/{case_id}/decision")
async def case_decision(case_id: str, req: DecisionRequest):
    if case_id not in CASES:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    if req.decision not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="decision must be approve or reject")
    case = CASES[case_id]
    case["status"] = "closed"
    case["reviewer_decision"] = req.decision
    case["reviewer_note"] = req.note
    case["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    return case

@app.get("/metrics")
async def get_metrics():
    metrics_path = os.path.join(_GEN, "metrics.json")
    if not os.path.exists(metrics_path):
        raise HTTPException(status_code=404, detail="metrics.json not found")
    with open(metrics_path) as f:
        data = json.load(f)
    data["api_uptime_seconds"] = round(time.time() - START_TIME, 1)
    return data

@app.get("/graph")
async def get_graph(account_id: str = Query(...), hops: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(100, ge=10, le=500)):
    if G is None or not G.has_node(account_id):
        raise HTTPException(status_code=404, detail=f"Account {account_id} not in graph")
    neighborhood = get_neighborhood(account_id, G, max_hops=hops, max_nodes=max_nodes)
    risk_raw = GRAPH_RISKS.get(account_id, {})
    cycles = [[account_id]] if risk_raw.get("in_cycle", False) else []
    fan_in_dict = {account_id: risk_raw.get("in_degree", 5)} if risk_raw.get("fan_in_flag", False) else {}
    shared_devices = {"SHARED": [account_id]} if risk_raw.get("shared_device_flag", False) else {}
    account_risk = get_account_graph_risk(account_id, G, cycles, fan_in_dict, shared_devices)
    return {"account": account_risk, "neighborhood": neighborhood}

@app.get("/health")
async def health():
    return {"status": "ok", "scored_count": len(SCORED_TRANSACTIONS),
            "open_cases": sum(1 for c in CASES.values() if c["status"] == "open")}