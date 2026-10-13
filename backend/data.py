import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Constants
RANDOM_SEED = 42
NUM_ACCOUNTS = 2000
NUM_TRANSACTIONS = 50000
TARGET_FRAUD_RATIO = 0.04  # 4%; print actual ratio and warn if outside 2–8%
FRAUD_AMOUNT_THRESHOLD = 50000  # used by structuring scenario
SHARED_BURNER_DEVICES = [f"DEV_SHARED_{i:02d}" for i in range(15)]  # shared device pool for ATO & mule scenarios

INDIAN_CITIES = [
    "Chennai", "Mumbai", "Delhi", "Bengaluru", "Hyderabad",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat"
]

# Intraday hourly probability distribution: peak between 08:00 and 22:00, low between 00:00 and 05:00
INTRADAY_HOURLY_WEIGHTS = np.array([
    0.008, 0.005, 0.004, 0.004, 0.006, 0.015, 0.030, 0.050,  # 00:00 - 07:00
    0.065, 0.070, 0.072, 0.068, 0.065, 0.062, 0.060, 0.065,  # 08:00 - 15:00
    0.070, 0.072, 0.075, 0.072, 0.065, 0.055, 0.040, 0.018   # 16:00 - 23:00
])
INTRADAY_HOURLY_WEIGHTS = INTRADAY_HOURLY_WEIGHTS / INTRADAY_HOURLY_WEIGHTS.sum()


def generate_accounts(rng: np.random.Generator):
    """Generates synthetic accounts DataFrame and account properties dictionary."""
    account_ids = [f"ACC{i:04d}" for i in range(NUM_ACCOUNTS)]
    home_cities = rng.choice(INDIAN_CITIES, size=NUM_ACCOUNTS)
    avg_monthly_txns = np.round(rng.lognormal(mean=10.5, sigma=0.6, size=NUM_ACCOUNTS), 2)
    account_types = rng.choice(["personal", "business", "mule"], size=NUM_ACCOUNTS, p=[0.70, 0.20, 0.10])

    accounts_df = pd.DataFrame({
        "account_id": account_ids,
        "home_city": home_cities,
        "avg_monthly_txn": avg_monthly_txns,
        "account_type": account_types
    })

    # Generate 1-3 primary devices per account
    account_devices = {}
    for acc_id in account_ids:
        num_devices = int(rng.integers(1, 4))
        account_devices[acc_id] = [f"DEV_{acc_id}_{k}" for k in range(num_devices)]

    account_meta = {
        row["account_id"]: {
            "home_city": row["home_city"],
            "avg_monthly_txn": float(row["avg_monthly_txn"]),
            "account_type": row["account_type"],
            "devices": account_devices[row["account_id"]]
        }
        for _, row in accounts_df.iterrows()
    }

    return accounts_df, account_meta


def get_random_timestamp(rng: np.random.Generator, start_date: datetime, end_date: datetime) -> datetime:
    """Samples a datetime with realistic intraday distribution between start_date and end_date."""
    total_days = (end_date.date() - start_date.date()).days
    rand_day_offset = int(rng.integers(0, max(1, total_days + 1)))
    day = start_date.date() + timedelta(days=rand_day_offset)
    hour = int(rng.choice(24, p=INTRADAY_HOURLY_WEIGHTS))
    minute = int(rng.integers(0, 60))
    second = int(rng.integers(0, 60))
    dt = datetime(day.year, day.month, day.day, hour, minute, second)
    if dt < start_date:
        return start_date
    if dt > end_date:
        return end_date
    return dt


def sample_timestamps_vectorized(rng: np.random.Generator, n: int, start_dt: datetime, end_dt: datetime):
    """Vectorized sampling of ISO timestamps conforming to intraday hourly distribution."""
    total_days = (end_dt.date() - start_dt.date()).days
    rand_days = rng.integers(0, max(1, total_days + 1), size=n)
    rand_hours = rng.choice(24, size=n, p=INTRADAY_HOURLY_WEIGHTS)
    rand_mins = rng.integers(0, 60, size=n)
    rand_secs = rng.integers(0, 60, size=n)

    base_ts = pd.to_datetime(start_dt.date())
    delta_seconds = rand_days * 86400 + rand_hours * 3600 + rand_mins * 60 + rand_secs
    timestamps = (base_ts + pd.to_timedelta(delta_seconds, unit="s")).strftime("%Y-%m-%dT%H:%M:%S")
    return timestamps.tolist()


def generate_synthetic_data():
    """Main generation pipeline creating accounts, planting scenarios, adding noise, and exporting."""
    rng = np.random.default_rng(RANDOM_SEED)

    start_date = datetime(2026, 1, 1, 0, 0, 0)
    end_date = datetime(2026, 10, 13, 23, 59, 59)
    window_30d_start = datetime(2026, 9, 14, 0, 0, 0)

    # 1. Accounts Generation
    accounts_df, account_meta = generate_accounts(rng)
    all_account_ids = accounts_df["account_id"].tolist()
    mule_account_ids = accounts_df[accounts_df["account_type"] == "mule"]["account_id"].tolist()
    personal_account_ids = accounts_df[accounts_df["account_type"] == "personal"]["account_id"].tolist()
    business_account_ids = accounts_df[accounts_df["account_type"] == "business"]["account_id"].tolist()

    # Fast account index lookup
    acc_to_idx = {acc: i for i, acc in enumerate(all_account_ids)}

    def get_other_account(sender_id: str) -> str:
        s_idx = acc_to_idx[sender_id]
        offset = int(rng.integers(1, NUM_ACCOUNTS))
        r_idx = (s_idx + offset) % NUM_ACCOUNTS
        return all_account_ids[r_idx]

    transactions = []

    # -------------------------------------------------------------
    # Scenario 1: account_takeover (~0.5% -> exactly 250 rows)
    # - device_id not seen before for sender (50% shared burner devices, 50% brand new)
    # - city differs from sender's home_city
    # - amount >= 3 * (sender's avg_monthly_txn / 30)
    # -------------------------------------------------------------
    num_ato = 250
    num_ato_shared = num_ato // 2  # 125
    num_ato_unseen = num_ato - num_ato_shared  # 125

    num_ato_clusters = 10
    cluster_dates = [
        get_random_timestamp(rng, start_date, end_date - timedelta(days=2))
        for _ in range(num_ato_clusters)
    ]
    ato_candidates = [acc for acc in all_account_ids if acc not in mule_account_ids]

    # Shared burner ATOs
    for i in range(num_ato_shared):
        base_time = cluster_dates[i % num_ato_clusters]
        txn_time = base_time + timedelta(
            hours=int(rng.integers(0, 24)),
            minutes=int(rng.integers(0, 60)),
            seconds=int(rng.integers(0, 60))
        )
        sender = str(rng.choice(ato_candidates))
        device = str(rng.choice(SHARED_BURNER_DEVICES[:8]))
        sender_city = account_meta[sender]["home_city"]
        other_cities = [c for c in INDIAN_CITIES if c != sender_city]
        city = str(rng.choice(other_cities))
        sender_avg = account_meta[sender]["avg_monthly_txn"]
        amount = round(float(rng.uniform(3.0, 6.0) * (sender_avg / 30.0)), 2)
        amount = max(amount, 3500.0)
        receiver = get_other_account(sender)

        transactions.append({
            "timestamp": txn_time.isoformat(),
            "sender_id": sender,
            "receiver_id": receiver,
            "amount": amount,
            "device_id": device,
            "city": city,
            "is_fraud": 1,
            "fraud_type": "account_takeover"
        })

    # Unseen unique device ATOs
    for i in range(num_ato_unseen):
        txn_time = get_random_timestamp(rng, start_date, end_date)
        sender = str(rng.choice(ato_candidates))
        device = f"DEV_ATO_UNSEEN_{i:04d}"
        sender_city = account_meta[sender]["home_city"]
        other_cities = [c for c in INDIAN_CITIES if c != sender_city]
        city = str(rng.choice(other_cities))
        sender_avg = account_meta[sender]["avg_monthly_txn"]
        amount = round(float(rng.uniform(3.0, 6.5) * (sender_avg / 30.0)), 2)
        amount = max(amount, 3500.0)
        receiver = get_other_account(sender)

        transactions.append({
            "timestamp": txn_time.isoformat(),
            "sender_id": sender,
            "receiver_id": receiver,
            "amount": amount,
            "device_id": device,
            "city": city,
            "is_fraud": 1,
            "fraud_type": "account_takeover"
        })

    # -------------------------------------------------------------
    # Scenario 2: structuring (~0.8% -> 400 rows)
    # 20 senders making 20 transfers each within 48 hours
    # Bursts: count_10m >= 3, count_1h >= 8
    # amount in [45000, 49999], receivers different each time
    # -------------------------------------------------------------
    num_structuring_senders = 20
    txns_per_structuring = 20  # 20 * 20 = 400 rows
    structuring_senders = rng.choice(
        [a for a in all_account_ids if a not in mule_account_ids],
        size=num_structuring_senders,
        replace=False
    )

    offsets_minutes = [
        0, 2, 5, 8,
        16, 24, 32, 41, 52,
        120, 240, 360, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700
    ]

    for sender in structuring_senders:
        burst_start = get_random_timestamp(rng, start_date, end_date - timedelta(hours=48))
        sender_city = account_meta[sender]["home_city"]
        sender_device = str(rng.choice(account_meta[sender]["devices"]))

        # Pick 20 distinct receivers
        s_idx = acc_to_idx[sender]
        rec_offsets = rng.choice(np.arange(1, NUM_ACCOUNTS), size=txns_per_structuring, replace=False)
        receivers = [all_account_ids[(s_idx + off) % NUM_ACCOUNTS] for off in rec_offsets]

        for idx in range(txns_per_structuring):
            t_offset = offsets_minutes[idx]
            txn_time = burst_start + timedelta(
                minutes=t_offset,
                seconds=int(rng.integers(0, 50))
            )
            amount = round(float(rng.uniform(45000.0, 49999.0)), 2)
            receiver = str(receivers[idx])

            transactions.append({
                "timestamp": txn_time.isoformat(),
                "sender_id": sender,
                "receiver_id": receiver,
                "amount": amount,
                "device_id": sender_device,
                "city": sender_city,
                "is_fraud": 1,
                "fraud_type": "structuring"
            })

    # -------------------------------------------------------------
    # Scenario 3: circular_transfers (~0.6% -> 300 rows)
    # 48 cycles of len 3 (144) + 39 cycles of len 4 (156) = 300 rows
    # >= 60% in final 30 days (2026-09-14 to 2026-10-13)
    # Legs within 2 hours, decaying amounts (0.92-0.98)
    # -------------------------------------------------------------
    total_cycles = 48 + 39
    num_cycles_in_final_30d = int(np.ceil(0.65 * total_cycles))  # 57 cycles (~65.5% >= 60%)

    cycle_lengths = [3] * 48 + [4] * 39
    rng.shuffle(cycle_lengths)

    for i, c_len in enumerate(cycle_lengths):
        if i < num_cycles_in_final_30d:
            cycle_start = get_random_timestamp(rng, window_30d_start, end_date - timedelta(hours=10))
        else:
            cycle_start = get_random_timestamp(rng, start_date, window_30d_start - timedelta(hours=10))

        cycle_nodes = rng.choice(all_account_ids, size=c_len, replace=False)
        base_amount = round(float(rng.uniform(50000.0, 200000.0)), 2)
        curr_time = cycle_start
        curr_amount = base_amount

        for hop in range(c_len):
            u = str(cycle_nodes[hop])
            v = str(cycle_nodes[(hop + 1) % c_len])
            u_device = str(rng.choice(account_meta[u]["devices"]))
            u_city = account_meta[u]["home_city"]

            transactions.append({
                "timestamp": curr_time.isoformat(),
                "sender_id": u,
                "receiver_id": v,
                "amount": curr_amount,
                "device_id": u_device,
                "city": u_city,
                "is_fraud": 1,
                "fraud_type": "circular"
            })

            hop_delay_mins = int(rng.integers(15, 95))  # within 2 hours
            curr_time = curr_time + timedelta(minutes=hop_delay_mins)
            decay_factor = float(rng.uniform(0.92, 0.98))
            curr_amount = round(curr_amount * decay_factor, 2)

    # -------------------------------------------------------------
    # Scenario 4: mule_accounts (~1.0% -> exactly 500 rows)
    # 20 accounts where account_type == "mule"
    # >= 70% mule bursts in final 30 days
    # 5-15 inbound senders within 4-hour window, burner reuse
    # 1-3 outbound cash-outs within 2 hours
    # -------------------------------------------------------------
    selected_mules = rng.choice(mule_account_ids, size=20, replace=False)
    mule_burst_specs = []
    for mule in selected_mules:
        mule_burst_specs.append(mule)
        mule_burst_specs.append(mule)

    total_mule_bursts = len(mule_burst_specs)  # 40 bursts
    num_mule_in_30d = int(np.ceil(0.75 * total_mule_bursts))  # 30 bursts (75% >= 70%)

    base_inbound_counts = rng.integers(8, 14, size=total_mule_bursts)
    outbound_counts = rng.integers(1, 3, size=total_mule_bursts)
    current_mule_total = int(np.sum(base_inbound_counts) + np.sum(outbound_counts))
    diff = 500 - current_mule_total
    idx_adjust = 0
    while diff != 0 and idx_adjust < total_mule_bursts:
        if diff > 0 and base_inbound_counts[idx_adjust] < 15:
            base_inbound_counts[idx_adjust] += 1
            diff -= 1
        elif diff < 0 and base_inbound_counts[idx_adjust] > 5:
            base_inbound_counts[idx_adjust] -= 1
            diff += 1
        idx_adjust = (idx_adjust + 1) % total_mule_bursts

    for b_idx, mule in enumerate(mule_burst_specs):
        if b_idx < num_mule_in_30d:
            burst_start = get_random_timestamp(rng, window_30d_start, end_date - timedelta(hours=8))
        else:
            burst_start = get_random_timestamp(rng, start_date, window_30d_start - timedelta(hours=8))

        num_inbound = int(base_inbound_counts[b_idx])
        num_outbound = int(outbound_counts[b_idx])

        # Pick distinct senders
        eligible_senders = [a for a in all_account_ids if a != mule]
        inbound_senders = rng.choice(eligible_senders, size=num_inbound, replace=False)

        num_shared_burners = int(min(rng.integers(3, 6), num_inbound))
        burner_subset = rng.choice(SHARED_BURNER_DEVICES, size=num_shared_burners, replace=True)

        inbound_amounts = []
        last_inbound_time = burst_start

        for s_idx, sender in enumerate(inbound_senders):
            offset_mins = int(rng.integers(0, 240))  # within 4 hours
            txn_time = burst_start + timedelta(minutes=offset_mins, seconds=int(rng.integers(0, 60)))
            if txn_time > last_inbound_time:
                last_inbound_time = txn_time

            amt = round(float(rng.uniform(10000.0, 45000.0)), 2)
            inbound_amounts.append(amt)

            if s_idx < num_shared_burners:
                device = str(burner_subset[s_idx])
            else:
                device = str(rng.choice(account_meta[sender]["devices"]))

            sender_city = account_meta[sender]["home_city"]

            transactions.append({
                "timestamp": txn_time.isoformat(),
                "sender_id": sender,
                "receiver_id": mule,
                "amount": amt,
                "device_id": device,
                "city": sender_city,
                "is_fraud": 1,
                "fraud_type": "mule"
            })

        total_inbound = sum(inbound_amounts)
        cash_out_total = total_inbound * float(rng.uniform(0.92, 0.96))
        cash_out_split = cash_out_total / num_outbound

        cashout_receivers = rng.choice(
            [a for a in all_account_ids if a != mule and a not in inbound_senders],
            size=num_outbound,
            replace=False
        )

        for o_idx in range(num_outbound):
            out_offset_mins = int(rng.integers(5, 120))  # within 2 hours
            out_time = last_inbound_time + timedelta(minutes=out_offset_mins, seconds=int(rng.integers(0, 60)))
            out_amt = round(float(cash_out_split * rng.uniform(0.97, 1.03)), 2)
            out_receiver = str(cashout_receivers[o_idx])
            mule_device = str(rng.choice(account_meta[mule]["devices"]))
            mule_city = account_meta[mule]["home_city"]

            transactions.append({
                "timestamp": out_time.isoformat(),
                "sender_id": mule,
                "receiver_id": out_receiver,
                "amount": out_amt,
                "device_id": mule_device,
                "city": mule_city,
                "is_fraud": 1,
                "fraud_type": "mule"
            })

    planted_fraud_count = len(transactions)  # 250 + 400 + 300 + 500 = 1450 rows
    remaining_legitimate_needed = NUM_TRANSACTIONS - planted_fraud_count  # 48550 rows

    # -------------------------------------------------------------
    # Scenario 5: legitimate_unusual (NOT fraud — is_fraud=0, fraud_type="none")
    # & Everyday honest transactions
    # -------------------------------------------------------------
    legit_transactions = []

    # 5a. Salary transfers: 1 large transfer per account per month (25000 - 80000)
    salary_accounts = personal_account_ids[:400]
    for month in range(1, 11):
        for acc in salary_accounts:
            s_day = int(rng.integers(1, 6))
            s_hour = int(rng.integers(9, 17))
            s_min = int(rng.integers(0, 60))
            s_sec = int(rng.integers(0, 60))
            s_time = datetime(2026, month, s_day, s_hour, s_min, s_sec)
            amount = round(float(rng.uniform(25000.0, 80000.0)), 2)
            payer = str(rng.choice(business_account_ids))
            payer_city = account_meta[payer]["home_city"]
            payer_device = str(rng.choice(account_meta[payer]["devices"]))

            legit_transactions.append({
                "timestamp": s_time.isoformat(),
                "sender_id": payer,
                "receiver_id": acc,
                "amount": amount,
                "device_id": payer_device,
                "city": payer_city,
                "is_fraud": 0,
                "fraud_type": "none"
            })

    # 5b. Festival spends: clustered in March (Holi) and October (Diwali)
    num_festival_txns = 1500
    for _ in range(num_festival_txns):
        if rng.random() < 0.5:
            f_month = 3
            f_day = int(rng.integers(10, 26))
        else:
            f_month = 10
            f_day = int(rng.integers(1, 13))

        f_hour = int(rng.choice(24, p=INTRADAY_HOURLY_WEIGHTS))
        f_min = int(rng.integers(0, 60))
        f_sec = int(rng.integers(0, 60))
        f_time = datetime(2026, f_month, f_day, f_hour, f_min, f_sec)

        sender = str(rng.choice(personal_account_ids))
        receiver = get_other_account(sender)
        amount = round(float(rng.uniform(15000.0, 60000.0)), 2)
        device = str(rng.choice(account_meta[sender]["devices"]))
        city = account_meta[sender]["home_city"]

        legit_transactions.append({
            "timestamp": f_time.isoformat(),
            "sender_id": sender,
            "receiver_id": receiver,
            "amount": amount,
            "device_id": device,
            "city": city,
            "is_fraud": 0,
            "fraud_type": "none"
        })

    # 5c. College fees: one-off transfers >= 100000 from personal accounts
    num_college_txns = 350
    college_senders = rng.choice(personal_account_ids, size=num_college_txns, replace=False)
    for sender in college_senders:
        c_month = int(rng.integers(6, 9))
        c_day = int(rng.integers(1, 29))
        c_hour = int(rng.integers(10, 16))
        c_min = int(rng.integers(0, 60))
        c_time = datetime(2026, c_month, c_day, c_hour, c_min, int(rng.integers(0, 60)))
        amount = round(float(rng.uniform(100000.0, 250000.0)), 2)
        receiver = str(rng.choice(business_account_ids))
        device = str(rng.choice(account_meta[sender]["devices"]))
        city = account_meta[sender]["home_city"]

        legit_transactions.append({
            "timestamp": c_time.isoformat(),
            "sender_id": sender,
            "receiver_id": receiver,
            "amount": amount,
            "device_id": device,
            "city": city,
            "is_fraud": 0,
            "fraud_type": "none"
        })

    # 5d. Everyday honest transactions (vectorized for maximum performance)
    needed_everyday = remaining_legitimate_needed - len(legit_transactions)

    sender_indices = rng.integers(0, NUM_ACCOUNTS, size=needed_everyday)
    receiver_offsets = rng.integers(1, NUM_ACCOUNTS, size=needed_everyday)
    receiver_indices = (sender_indices + receiver_offsets) % NUM_ACCOUNTS

    sender_ids = [all_account_ids[i] for i in sender_indices]
    receiver_ids = [all_account_ids[i] for i in receiver_indices]

    daily_amts = np.array([account_meta[s]["avg_monthly_txn"] / 30.0 for s in sender_ids])
    large_one_off_mask = rng.random(size=needed_everyday) < 0.005

    scale_amts = np.maximum(daily_amts * 0.4, 50.0)
    exp_amts = rng.exponential(scale=scale_amts) + rng.uniform(50.0, 300.0, size=needed_everyday)
    normal_amts = np.clip(exp_amts, 10.0, 45000.0)
    large_amts = rng.uniform(5.0, 10.0, size=needed_everyday) * daily_amts
    final_amts = np.where(large_one_off_mask, large_amts, normal_amts)
    final_amts = np.round(final_amts, 2).tolist()

    ts_strings = sample_timestamps_vectorized(rng, needed_everyday, start_date, end_date)

    dev_list = [str(rng.choice(account_meta[s]["devices"])) for s in sender_ids]

    travel_mask = rng.random(size=needed_everyday) < 0.05
    cities = []
    for idx, s in enumerate(sender_ids):
        h_city = account_meta[s]["home_city"]
        if travel_mask[idx]:
            other_c = [c for c in INDIAN_CITIES if c != h_city]
            cities.append(str(rng.choice(other_c)))
        else:
            cities.append(h_city)

    everyday_df = pd.DataFrame({
        "timestamp": ts_strings,
        "sender_id": sender_ids,
        "receiver_id": receiver_ids,
        "amount": final_amts,
        "device_id": dev_list,
        "city": cities,
        "is_fraud": 0,
        "fraud_type": "none"
    })

    # Combine planted fraud, legitimate unusual, and everyday transactions
    planted_df = pd.DataFrame(transactions)
    legit_df = pd.DataFrame(legit_transactions)
    df = pd.concat([planted_df, legit_df, everyday_df], ignore_index=True)

    # -------------------------------------------------------------
    # Step 5: Noise / Overlap
    # - Randomly flip 3% of fraud rows (is_fraud == 1) to is_fraud=0, fraud_type="none"
    # - Randomly flip 1.5%–2% of legitimate rows (is_fraud == 0) to is_fraud=1, fraud_type="noise"
    #   so overall actual_fraud_ratio lands cleanly around 0.04 (within [0.02, 0.08])
    # -------------------------------------------------------------
    fraud_indices = df[df["is_fraud"] == 1].index.to_numpy()
    num_flip_fraud = int(round(0.03 * len(fraud_indices)))

    if num_flip_fraud > 0:
        flip_to_legit = rng.choice(fraud_indices, size=num_flip_fraud, replace=False)
        df.loc[flip_to_legit, "is_fraud"] = 0
        df.loc[flip_to_legit, "fraud_type"] = "none"

    legit_indices = df[df["is_fraud"] == 0].index.to_numpy()
    flip_noise_rate = 0.0155  # 1.55%, within [1.5%, 2.0%]
    num_flip_noise = int(round(flip_noise_rate * len(legit_indices)))

    flip_to_noise = rng.choice(legit_indices, size=num_flip_noise, replace=False)
    df.loc[flip_to_noise, "is_fraud"] = 1
    df.loc[flip_to_noise, "fraud_type"] = "noise"

    # -------------------------------------------------------------
    # Step 6: Sorting, Transaction IDs, and Export
    # Re-assign transaction_id sequentially after sorting by timestamp ascending
    # -------------------------------------------------------------
    df = df.sort_values(by="timestamp", ascending=True).reset_index(drop=True)
    df["transaction_id"] = [f"TX{i:06d}" for i in range(len(df))]

    col_order = [
        "transaction_id", "timestamp", "sender_id", "receiver_id",
        "amount", "device_id", "city", "is_fraud", "fraud_type"
    ]
    df = df[col_order]

    # Save CSVs
    out_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(out_dir, exist_ok=True)

    accounts_file = os.path.join(out_dir, "accounts.csv")
    transactions_file = os.path.join(out_dir, "transactions.csv")
    metadata_file = os.path.join(out_dir, "generation_metadata.json")

    accounts_df.to_csv(accounts_file, index=False)
    df.to_csv(transactions_file, index=False)

    # Compute summary stats
    total_txns = len(df)
    fraud_count = int(df["is_fraud"].sum())
    actual_fraud_ratio = round(float(fraud_count / total_txns), 4)
    counts_per_type = df["fraud_type"].value_counts().to_dict()

    metadata = {
        "random_seed": RANDOM_SEED,
        "num_accounts": NUM_ACCOUNTS,
        "num_transactions": total_txns,
        "actual_fraud_ratio": actual_fraud_ratio,
        "counts_per_type": counts_per_type,
        "generated_at": datetime.now().isoformat()
    }

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    # Print summary to stdout
    print("=" * 60)
    print("DATA GENERATION SUMMARY")
    print("=" * 60)
    print(f"Total Transactions: {total_txns}")
    print(f"Total Fraud Count:  {fraud_count}")
    print(f"Actual Fraud Ratio: {actual_fraud_ratio:.2%} (Target: {TARGET_FRAUD_RATIO:.2%})")
    print("\nCounts per fraud_type:")
    for ftype, count in counts_per_type.items():
        print(f"  - {ftype:<20}: {count}")

    if actual_fraud_ratio < 0.02 or actual_fraud_ratio > 0.08:
        print(f"\n[WARNING] Actual fraud ratio {actual_fraud_ratio:.2%} is outside [2%, 8%]!")
    else:
        print(f"\n[OK] Actual fraud ratio {actual_fraud_ratio:.2%} is within [2%, 8%].")

    planted_scenarios = ["account_takeover", "structuring", "circular", "mule"]
    all_scenarios_present = True
    for sc in planted_scenarios:
        count = counts_per_type.get(sc, 0)
        if count >= 1:
            print(f"[OK] Scenario '{sc}' verified with {count} instances (>= 1).")
        else:
            print(f"[FAIL] Scenario '{sc}' missing or 0 instances!")
            all_scenarios_present = False

    print("=" * 60)
    print(f"Accounts saved to:     {accounts_file}")
    print(f"Transactions saved to: {transactions_file}")
    print(f"Metadata saved to:     {metadata_file}")
    print("=" * 60)

    return accounts_df, df, metadata


if __name__ == "__main__":
    generate_synthetic_data()
