import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

"""
backend/features.py
-------------------
Feature engineering for the Real-Time Fraud & AML Risk Orchestration prototype.

Computes 6 strictly past-only features per transaction row using incremental
per-sender state dictionaries — O(N) overall, no full-DataFrame scans inside the loop.
"""

from collections import defaultdict, deque
from typing import Optional

import pandas as pd

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False


def get_feature_columns() -> list:
    """Returns the exact 6 feature names in the order the model expects them."""
    return ["amount_vs_sender_avg", "new_device", "new_payee", "city_change", "count_10m", "count_1h"]


def compute_features(
    transactions_df: pd.DataFrame,
    accounts_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute 6 fraud-detection features for every row in transactions_df using
    strictly past-only (no look-ahead) incremental per-sender state.

    Parameters
    ----------
    transactions_df : pd.DataFrame
        Must contain columns: transaction_id, timestamp, sender_id, receiver_id,
        amount, device_id, city, is_fraud, fraud_type.
    accounts_df : pd.DataFrame, optional
        Accounts metadata (currently unused but accepted for API compatibility).

    Returns
    -------
    pd.DataFrame
        Copy of transactions_df sorted ascending by timestamp with 6 new columns.
    """
    # ----------------------------------------------------------------
    # 1. Sort by timestamp ascending, reset index
    # ----------------------------------------------------------------
    df = transactions_df.copy()
    df["_ts"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("_ts", ascending=True).reset_index(drop=True)

    n = len(df)

    # Pre-allocate output arrays
    amount_vs_sender_avg_arr = [1.0] * n
    new_device_arr           = [0]   * n
    new_payee_arr            = [0]   * n
    city_change_arr          = [0]   * n
    count_10m_arr            = [0]   * n
    count_1h_arr             = [0]   * n

    # ----------------------------------------------------------------
    # 2. Per-sender incremental state dictionaries
    #
    # State flushed on STRICTLY NEWER timestamp to avoid same-second look-ahead.
    # Each sender has a "pending" buffer for current-second events and a
    # "committed" historical state for events strictly in the past.
    # ----------------------------------------------------------------

    # Committed (past-only) state — available to current row
    # amount history: sum & count for mean
    sender_amt_sum   = defaultdict(float)   # sum of past amounts
    sender_amt_cnt   = defaultdict(int)     # count of past transactions

    # device sets seen so far (past only)
    sender_devices   = defaultdict(set)

    # (sender, receiver) pairs seen so far (past only)
    payee_pairs      = set()

    # city frequency Counter (past only): sender -> dict{city -> count}
    sender_city_cnt  = defaultdict(lambda: defaultdict(int))

    # Sliding window deques of past UNIX-second timestamps for 10m / 1h windows
    # Each deque entry: int (timestamp as Unix second)
    sender_ts_deque  = defaultdict(deque)   # deque of past epoch-seconds

    # ----------------------------------------------------------------
    # Pending buffer: holds tuples (idx, ts_epoch_s, amount, device_id, receiver_id, city)
    # for rows at the SAME second as the last-seen timestamp for this sender.
    # These are NOT yet committed; they become committed when a later timestamp arrives.
    # ----------------------------------------------------------------
    sender_pending   = defaultdict(list)     # sender -> list of (idx, epoch_s, amt, dev, rcv, city)
    sender_last_ts   = defaultdict(lambda: -1)   # last epoch-second seen per sender

    _10MIN_S = 600   # 10 minutes in seconds
    _1H_S    = 3600  # 60 minutes in seconds

    def _flush_pending(sid: str, up_to_epoch: int) -> None:
        """
        Commit all pending rows for sender `sid` whose timestamp is strictly less
        than `up_to_epoch`.  Called before processing a new row.
        """
        pending = sender_pending[sid]
        if not pending:
            return
        # If pending timestamp is strictly less than the new row's timestamp,
        # commit all pending rows to the committed state.
        # All pending entries share the same epoch second (by construction).
        if pending[0][1] < up_to_epoch:
            dq = sender_ts_deque[sid]
            for _, ep, amt, dev, rcv, city in pending:
                sender_amt_sum[sid] += amt
                sender_amt_cnt[sid] += 1
                sender_devices[sid].add(dev)
                payee_pairs.add((sid, rcv))
                sender_city_cnt[sid][city] += 1
                dq.append(ep)
            sender_pending[sid] = []

    def _prune_deque(sid: str, current_epoch: int) -> None:
        """Remove entries from the sliding window deque that are outside the 1h window."""
        dq = sender_ts_deque[sid]
        cutoff_1h = current_epoch - _1H_S
        while dq and dq[0] < cutoff_1h:
            dq.popleft()

    # ----------------------------------------------------------------
    # 3. Main loop — O(N) with small per-sender overhead
    # ----------------------------------------------------------------
    sender_col    = df["sender_id"].tolist()
    receiver_col  = df["receiver_id"].tolist()
    amount_col    = df["amount"].tolist()
    device_col    = df["device_id"].tolist()
    city_col      = df["city"].tolist()
    ts_col        = df["_ts"].tolist()   # numpy datetime64 → will call .timestamp()

    if _HAS_TQDM:
        row_iter = tqdm(range(n), desc="Computing features", unit="rows", ncols=80)
    else:
        row_iter = range(n)

    for i in row_iter:
        sid   = sender_col[i]
        rcv   = receiver_col[i]
        amt   = float(amount_col[i])
        dev   = device_col[i]
        city  = city_col[i]

        # Convert numpy datetime64 → float epoch-seconds
        ts_epoch = int(pd.Timestamp(ts_col[i]).timestamp())

        # -- Flush pending rows for this sender if new timestamp is strictly greater --
        _flush_pending(sid, ts_epoch)

        # -- Prune sliding window deque to 1h window --
        _prune_deque(sid, ts_epoch)

        # -- Compute features using committed (past-only) state --

        # 1. amount_vs_sender_avg
        cnt = sender_amt_cnt[sid]
        if cnt > 0:
            prior_mean = sender_amt_sum[sid] / cnt
            amount_vs_sender_avg_arr[i] = round(amt / prior_mean, 6) if prior_mean != 0 else 1.0
        else:
            amount_vs_sender_avg_arr[i] = 1.0

        # 2. new_device
        new_device_arr[i] = 0 if dev in sender_devices[sid] else 1

        # 3. new_payee
        new_payee_arr[i] = 0 if (sid, rcv) in payee_pairs else 1

        # 4. city_change — modal city from past history; tie or no history → 0
        city_hist = sender_city_cnt[sid]
        if city_hist:
            max_cnt = max(city_hist.values())
            modes = [c for c, v in city_hist.items() if v == max_cnt]
            if len(modes) == 1:
                city_change_arr[i] = 0 if city == modes[0] else 1
            else:
                city_change_arr[i] = 0  # tie → 0
        else:
            city_change_arr[i] = 0  # no history → 0

        # 5. count_10m — count of sender's prior events in [ts_epoch - 600, ts_epoch)
        dq = sender_ts_deque[sid]
        cutoff_10m = ts_epoch - _10MIN_S
        # Count entries in deque within (cutoff_10m, ts_epoch)
        # Deque is already pruned to 1h; count elements >= cutoff_10m
        c10 = 0
        for t in dq:
            if t >= cutoff_10m:
                c10 += 1
        count_10m_arr[i] = c10
        count_1h_arr[i]  = len(dq)  # all remaining entries are within 1h window

        # -- Add current row to pending buffer (NOT yet committed) --
        last_ts = sender_last_ts[sid]
        if last_ts == ts_epoch:
            # Same second as previous row(s) for this sender — add to pending
            sender_pending[sid].append((i, ts_epoch, amt, dev, rcv, city))
        else:
            # New timestamp for this sender — flush if any prior pending
            # (already done above), start fresh pending buffer
            sender_last_ts[sid] = ts_epoch
            sender_pending[sid] = [(i, ts_epoch, amt, dev, rcv, city)]

        if not _HAS_TQDM and (i + 1) % 10000 == 0:
            print(f"  Progress: {i + 1:,} / {n:,} rows processed")

    # ----------------------------------------------------------------
    # 4. Assign feature arrays to DataFrame
    # ----------------------------------------------------------------
    df["amount_vs_sender_avg"] = amount_vs_sender_avg_arr
    df["new_device"]           = new_device_arr
    df["new_payee"]            = new_payee_arr
    df["city_change"]          = city_change_arr
    df["count_10m"]            = count_10m_arr
    df["count_1h"]             = count_1h_arr

    # Drop the internal _ts helper column
    df = df.drop(columns=["_ts"])

    return df


# ----------------------------------------------------------------
# __main__ block
# ----------------------------------------------------------------
if __name__ == "__main__":
    import time

    _DIR = os.path.dirname(__file__)
    _GEN = os.path.join(_DIR, "generated")

    print("Loading data...")
    transactions_df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    accounts_df     = pd.read_csv(os.path.join(_GEN, "accounts.csv"))

    print(f"Transactions loaded: {len(transactions_df):,} rows")

    t0 = time.time()
    features_df = compute_features(transactions_df, accounts_df)
    elapsed = time.time() - t0

    feature_cols = get_feature_columns()

    print(f"\nFeature computation complete in {elapsed:.2f}s")
    print(f"Output shape: {features_df.shape}")
    print("\nFirst 3 rows — transaction_id, timestamp, and 6 feature columns:")
    display_cols = ["transaction_id", "timestamp"] + feature_cols
    print(features_df[display_cols].head(3).to_string(index=False))
