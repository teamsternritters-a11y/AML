import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import argparse
import json
import time
import httpx
import numpy as np
import pandas as pd
from tqdm import tqdm

_DIR = os.path.dirname(__file__)
_GEN = os.path.join(_DIR, "generated")
_BASE_URL = "http://localhost:8000"

def _parse_args():
    parser = argparse.ArgumentParser(description="Replay transactions through /score endpoint")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--delay", type=float, default=0.05)
    return parser.parse_args()

def _score_distribution(scores):
    buckets = {f"{lo}-{lo+10}": 0 for lo in range(0, 100, 10)}
    for s in scores:
        idx = min(int(s // 10), 9)
        key = f"{idx * 10}-{idx * 10 + 10}"
        buckets[key] += 1
    return buckets

def main():
    args = _parse_args()
    print("Loading transactions...")
    df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    df["_ts"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("_ts", ascending=True).reset_index(drop=True)
    split_idx = int(0.70 * len(df))
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    sample_n = min(args.limit, len(test_df))
    sample_df = test_df.sample(n=sample_n, random_state=42).reset_index(drop=True)
    print(f"Test set: {len(test_df):,} rows | Sampling: {sample_n} rows | "
          f"Fraud prevalence: {sample_df['is_fraud'].mean():.1%}")
    latencies_ms = []
    risk_scores = []
    actions = []
    fraud_labels = []
    errors = []
    successes = 0
    client = httpx.Client(timeout=10.0)
    print(f"\nReplaying {sample_n} transactions against {_BASE_URL}/score ...\n")
    for _, row in tqdm(sample_df.iterrows(), total=sample_n, unit="tx", ncols=80):
        payload = {
            "transaction_id": str(row["transaction_id"]),
            "sender_id":      str(row["sender_id"]),
            "receiver_id":    str(row["receiver_id"]),
            "amount":         float(row["amount"]),
            "device_id":      str(row["device_id"]),
            "city":           str(row["city"]),
            "timestamp":      str(row["timestamp"]),
        }
        t0 = time.perf_counter()
        try:
            resp = client.post(f"{_BASE_URL}/score", json=payload)
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                latencies_ms.append(latency_ms)
                risk_scores.append(float(data.get("risk_score", 0)))
                actions.append(str(data.get("action", "UNKNOWN")))
                fraud_labels.append(int(row["is_fraud"]))
                successes += 1
            else:
                errors.append({"tx": row["transaction_id"], "status": resp.status_code, "detail": resp.text[:200]})
        except Exception as exc:
            errors.append({"tx": row["transaction_id"], "error": str(exc)})
        time.sleep(args.delay)
    client.close()
    total_requests = sample_n
    error_count = len(errors)
    lat_arr = np.array(latencies_ms) if latencies_ms else np.array([0.0])
    mean_lat   = float(np.mean(lat_arr))
    median_lat = float(np.median(lat_arr))
    p95_lat    = float(np.percentile(lat_arr, 95))
    action_dist = {"ALLOW": 0, "OTP": 0, "HOLD": 0, "BLOCK": 0}
    for a in actions:
        action_dist[a] = action_dist.get(a, 0) + 1
    fraud_indices = [i for i, fl in enumerate(fraud_labels) if fl == 1]
    if fraud_indices:
        hold_block_on_fraud = sum(1 for i in fraud_indices if actions[i] in ("HOLD", "BLOCK"))
        fraud_recall = round(hold_block_on_fraud / len(fraud_indices), 4)
    else:
        fraud_recall = 0.0
    score_dist = _score_distribution(risk_scores)
    print("\n" + "=" * 60)
    print("REPLAY SUMMARY")
    print("=" * 60)
    print(f"  Total requests  : {total_requests}")
    print(f"  Successes       : {successes}")
    print(f"  Errors          : {error_count}")
    print(f"  Mean latency    : {mean_lat:.1f} ms")
    print(f"  Median latency  : {median_lat:.1f} ms")
    print(f"  P95 latency     : {p95_lat:.1f} ms")
    print(f"\n  Action distribution:")
    for act, cnt in sorted(action_dist.items()):
        pct = (cnt / successes * 100) if successes else 0
        print(f"    {act:<6}: {cnt:>4}  ({pct:.1f}%)")
    print(f"\n  Fraud recall (HOLD+BLOCK on is_fraud==1): {fraud_recall:.1%}")
    print(f"\n  Score distribution:")
    for bucket, cnt in score_dist.items():
        bar = "#" * min(cnt, 40)
        print(f"    {bucket:>7}: {cnt:>4}  {bar}")
    print("=" * 60)
    if errors:
        print(f"\n  First error sample: {errors[0]}")
    metrics_path = os.path.join(_GEN, "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            all_metrics = json.load(f)
    else:
        all_metrics = {}
    all_metrics["replay"] = {
        "total_requests": total_requests, "successes": successes, "errors": error_count,
        "mean_latency_ms": round(mean_lat, 2), "median_latency_ms": round(median_lat, 2),
        "p95_latency_ms": round(p95_lat, 2), "action_distribution": action_dist,
        "fraud_recall_hold_block": fraud_recall, "score_distribution": score_dist,
    }
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\n  metrics.json updated -> {metrics_path}")
    print("\nReplay complete.")

if __name__ == "__main__":
    main()