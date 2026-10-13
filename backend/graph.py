import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import time
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

"""
backend/graph.py
----------------
Graph-based fraud detection for the AML Risk Orchestration prototype.

Analyses a 30-day rolling transaction window to detect:
  - Circular transfers (A→B→C→A, etc.)
  - Fan-in mule patterns  (many senders → one receiver)
  - Shared device usage   (same device across multiple accounts within 24h)

No ML models or joblib artifacts are loaded here.
"""


# ──────────────────────────────────────────────────────────────────────────────
# 1. build_graph
# ──────────────────────────────────────────────────────────────────────────────

def build_graph(transactions_df: pd.DataFrame, max_days: int = 30) -> nx.DiGraph:
    """
    Build a directed transaction graph from the most recent `max_days` of data.

    Filtering to a rolling window reduces the graph size significantly for
    cycle detection — the full dataset would take orders of magnitude longer.

    Edge attributes are stored as lists to handle parallel edges (same sender
    → same receiver across multiple transactions), since DiGraph allows only
    one edge per (u, v) pair.

    Parameters
    ----------
    transactions_df : pd.DataFrame
        Must contain: timestamp, sender_id, receiver_id, transaction_id, amount.
    max_days : int
        Rolling window in days from the latest transaction timestamp.

    Returns
    -------
    nx.DiGraph
    """
    df = transactions_df.copy()
    df["_ts"] = pd.to_datetime(df["timestamp"])

    max_ts  = df["_ts"].max()
    cutoff  = max_ts - pd.Timedelta(days=max_days)
    df      = df[df["_ts"] >= cutoff].reset_index(drop=True)

    G = nx.DiGraph()

    for _, row in df.iterrows():
        u  = str(row["sender_id"])
        v  = str(row["receiver_id"])
        tx = str(row["transaction_id"])
        amt = float(row["amount"])

        if G.has_edge(u, v):
            # Append to existing lists — avoids overwriting parallel-edge data
            G[u][v]["transaction_ids"].append(tx)
            G[u][v]["amounts"].append(amt)
        else:
            G.add_edge(u, v, transaction_ids=[tx], amounts=[amt])

    return G


# ──────────────────────────────────────────────────────────────────────────────
# 2. detect_cycles
# ──────────────────────────────────────────────────────────────────────────────

def detect_cycles(G: nx.DiGraph, max_length: int = 4) -> list:
    """
    Find all simple cycles of length 2 to `max_length` in G.

    Uses nx.simple_cycles with `length_bound` when supported (NetworkX >= 3.2),
    falling back to manual length filtering for older versions.

    Time Guard: stops after 500 cycles OR 10 seconds to prevent hanging on
    dense graphs.

    Parameters
    ----------
    G : nx.DiGraph
    max_length : int
        Maximum cycle length to detect (inclusive).

    Returns
    -------
    list[list[str]]
        Each element is an ordered list of node IDs forming a cycle.
    """
    MAX_CYCLES  = 500
    TIME_LIMIT  = 10.0   # seconds

    cycles  = []
    t_start = time.time()

    try:
        # NetworkX >= 3.2 supports length_bound for early termination
        gen = nx.simple_cycles(G, length_bound=max_length)
    except TypeError:
        # Older NetworkX: iterate all cycles and filter by length
        gen = (c for c in nx.simple_cycles(G) if 2 <= len(c) <= max_length)

    for cycle in gen:
        if 2 <= len(cycle) <= max_length:
            cycles.append(cycle)

        if len(cycles) >= MAX_CYCLES:
            print(f"  [detect_cycles] Hit {MAX_CYCLES}-cycle cap — stopping early.")
            break

        if time.time() - t_start > TIME_LIMIT:
            print(f"  [detect_cycles] Hit {TIME_LIMIT}s time limit — stopping early.")
            break

    return cycles


# ──────────────────────────────────────────────────────────────────────────────
# 3. detect_fan_in
# ──────────────────────────────────────────────────────────────────────────────

def detect_fan_in(G: nx.DiGraph, min_senders: int = 5) -> dict:
    """
    Return accounts whose in-degree within G meets or exceeds `min_senders`.

    High in-degree in a transaction graph is a strong mule-account signal:
    many distinct senders funnelling money to a single receiver.

    Parameters
    ----------
    G : nx.DiGraph
    min_senders : int
        Minimum number of distinct senders required to flag an account.

    Returns
    -------
    dict[str, int]  — {account_id: in_degree}
    """
    return {
        node: deg
        for node, deg in G.in_degree()
        if deg >= min_senders
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. detect_shared_devices
# ──────────────────────────────────────────────────────────────────────────────

def detect_shared_devices(
    transactions_df: pd.DataFrame,
    window_hours: int = 24,
) -> dict:
    """
    Find devices used by >= 2 distinct sender accounts within any `window_hours`
    rolling window.

    Algorithm (O(N log N) per device):
      1. Group transactions by device_id.
      2. Sort each group by timestamp.
      3. Slide a window of `window_hours`; collect distinct senders within it.
      4. If >= 2 distinct senders appear in ANY window → flag the device.

    Parameters
    ----------
    transactions_df : pd.DataFrame
        Must contain: device_id, sender_id, timestamp.
    window_hours : int
        Window size in hours.

    Returns
    -------
    dict[str, list[str]]  — {device_id: [account_id, ...]}
        Sorted list of distinct senders who used the device within a window.
    """
    df = transactions_df.copy()
    df["_ts"] = pd.to_datetime(df["timestamp"])
    window_delta = pd.Timedelta(hours=window_hours)

    result: dict = {}

    # Group by device; process each device independently
    for device_id, grp in df.groupby("device_id"):
        grp = grp.sort_values("_ts").reset_index(drop=True)
        ts_arr      = grp["_ts"].tolist()
        sender_arr  = grp["sender_id"].tolist()
        n           = len(grp)

        left = 0
        window_senders: set = set()
        # Pre-load first row
        window_senders.add(sender_arr[0])

        for right in range(1, n):
            window_senders.add(sender_arr[right])

            # Shrink window from left while out of time bound
            while ts_arr[right] - ts_arr[left] > window_delta:
                # Remove left sender only if it has no other occurrence in window
                window_senders.discard(sender_arr[left])
                left += 1
                # Re-add any still-present senders (simple re-collect)
                window_senders = set(sender_arr[left : right + 1])

            if len(window_senders) >= 2:
                # Flag device: collect ALL distinct senders across entire device history
                all_senders = sorted(grp["sender_id"].unique().tolist())
                result[str(device_id)] = all_senders
                break   # No need to keep scanning this device

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 5. get_account_graph_risk
# ──────────────────────────────────────────────────────────────────────────────

def get_account_graph_risk(
    account_id: str,
    G: nx.DiGraph,
    cycles: list,
    fan_in: dict,
    shared_devices: dict,
) -> dict:
    """
    Compute a composite graph-based risk score for a single account.

    Risk components (additive, capped at 1.0):
        in_cycle           → +0.40  (circular transfer participant)
        fan_in_flag        → +0.35  (mule-like high in-degree)
        shared_device_flag → +0.25  (device shared with other accounts)

    Parameters
    ----------
    account_id    : str
    G             : nx.DiGraph  (30-day graph)
    cycles        : list[list[str]]
    fan_in        : dict[str, int]
    shared_devices: dict[str, list[str]]

    Returns
    -------
    dict with keys: account_id, in_degree, out_degree, in_cycle, fan_in_flag,
                    shared_device_flag, graph_risk
    """
    in_cycle = any(account_id in cycle for cycle in cycles)
    fan_in_flag = account_id in fan_in
    shared_device_flag = any(
        account_id in accs for accs in shared_devices.values()
    )

    score = 0.0
    if in_cycle:
        score += 0.40
    if fan_in_flag:
        score += 0.35
    if shared_device_flag:
        score += 0.25
    graph_risk = min(score, 1.0)

    return {
        "account_id":          account_id,
        "in_degree":           G.in_degree(account_id)  if G.has_node(account_id) else 0,
        "out_degree":          G.out_degree(account_id) if G.has_node(account_id) else 0,
        "in_cycle":            bool(in_cycle),
        "fan_in_flag":         bool(fan_in_flag),
        "shared_device_flag":  bool(shared_device_flag),
        "graph_risk":          float(graph_risk),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. precompute_all_risks
# ──────────────────────────────────────────────────────────────────────────────

def precompute_all_risks(
    G: nx.DiGraph,
    cycles: list,
    fan_in: dict,
    shared_devices: dict,
) -> dict:
    """
    Compute graph risk for every node in G and persist results.

    Also writes `graph_risk` back into each NetworkX node attribute so that
    `get_neighborhood` (and the UI) can read it directly from G without
    re-querying the JSON file.

    Saves output to backend/generated/graph_risks.json.

    Returns
    -------
    dict[str, dict]  — {account_id: risk_dict}
    """
    all_risks: dict = {}

    for account_id in G.nodes():
        risk_dict = get_account_graph_risk(
            account_id, G, cycles, fan_in, shared_devices
        )
        all_risks[account_id] = risk_dict

        # Write graph_risk back into the node so get_neighborhood can read it
        G.nodes[account_id]["graph_risk"] = risk_dict["graph_risk"]

    # Persist to disk
    out_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "graph_risks.json")

    with open(out_path, "w") as f:
        json.dump(all_risks, f, indent=2)

    print(f"  graph_risks.json saved -> {out_path}  ({len(all_risks):,} accounts)")

    return all_risks


# ──────────────────────────────────────────────────────────────────────────────
# 7. get_neighborhood
# ──────────────────────────────────────────────────────────────────────────────

def get_neighborhood(
    account_id: str,
    G: nx.DiGraph,
    max_hops: int = 2,
    max_nodes: int = 100,
) -> dict:
    """
    BFS neighbourhood subgraph up to `max_hops` from `account_id`.

    Uses an undirected BFS (follows both in- and out-edges) to capture the
    full local context of an account — both who sent money to it and who it
    sent money to.

    Parameters
    ----------
    account_id : str
    G          : nx.DiGraph  (with graph_risk stored on nodes from precompute_all_risks)
    max_hops   : int
    max_nodes  : int          Caps the response size for UI rendering.

    Returns
    -------
    dict with keys:
        nodes     : list[dict]   — [{"id": str, "graph_risk": float}, ...]
        edges     : list[dict]   — [{"source": str, "target": str,
                                      "amounts": list[float],
                                      "transaction_ids": list[str]}, ...]
        truncated : bool
    """
    if not G.has_node(account_id):
        return {"nodes": [], "edges": [], "truncated": False}

    # BFS over the undirected view so we follow edges in both directions
    visited_nodes = {account_id}
    frontier      = {account_id}
    truncated     = False

    for _ in range(max_hops):
        next_frontier: set = set()
        for node in frontier:
            # Successors (outbound edges)
            for nbr in G.successors(node):
                if nbr not in visited_nodes:
                    next_frontier.add(nbr)
            # Predecessors (inbound edges)
            for nbr in G.predecessors(node):
                if nbr not in visited_nodes:
                    next_frontier.add(nbr)

        for nbr in next_frontier:
            if len(visited_nodes) >= max_nodes:
                truncated = True
                break
            visited_nodes.add(nbr)

        if truncated:
            break

        frontier = next_frontier

    # Build node list with graph_risk from node attributes
    nodes = [
        {
            "id":         n,
            "graph_risk": float(G.nodes[n].get("graph_risk", 0.0)),
        }
        for n in visited_nodes
    ]

    # Build edge list — only edges where both endpoints are in visited_nodes
    edges = []
    for u, v, data in G.edges(data=True):
        if u in visited_nodes and v in visited_nodes:
            edges.append({
                "source":          u,
                "target":          v,
                "amounts":         data.get("amounts", []),
                "transaction_ids": data.get("transaction_ids", []),
            })

    return {
        "nodes":     nodes,
        "edges":     edges,
        "truncated": truncated,
    }


# ──────────────────────────────────────────────────────────────────────────────
# __main__
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _GEN = os.path.join(os.path.dirname(__file__), "generated")

    print("=" * 60)
    print("GRAPH ANALYSIS — Phase 4")
    print("=" * 60)

    # Load transactions
    print("\nLoading transactions...")
    tx_df = pd.read_csv(os.path.join(_GEN, "transactions.csv"))
    print(f"  {len(tx_df):,} rows loaded")

    # 1. Build 30-day graph
    print("\nBuilding 30-day graph...")
    t0 = time.time()
    G = build_graph(tx_df, max_days=30)
    print(f"  Nodes : {G.number_of_nodes():,}")
    print(f"  Edges : {G.number_of_edges():,}")
    print(f"  Built in {time.time() - t0:.2f}s")

    # 2. Detect cycles
    print("\nDetecting cycles (max_length=4, cap=500, timeout=10s)...")
    t0 = time.time()
    cycles = detect_cycles(G, max_length=4)
    print(f"  Cycles found : {len(cycles)}")
    print(f"  Detected in  : {time.time() - t0:.2f}s")
    if cycles:
        print(f"  Example cycle: {cycles[0]}")

    # 3. Detect fan-in mule accounts
    print("\nDetecting fan-in accounts (min_senders=5)...")
    fan_in = detect_fan_in(G, min_senders=5)
    print(f"  Fan-in accounts : {len(fan_in)}")
    if fan_in:
        top5 = sorted(fan_in.items(), key=lambda x: -x[1])[:5]
        print(f"  Top-5 by in-degree: {top5}")

    # 4. Detect shared devices (24-hour window, full dataset for coverage)
    print("\nDetecting shared devices (window=24h, full dataset)...")
    t0 = time.time()
    shared_devices = detect_shared_devices(tx_df, window_hours=24)
    print(f"  Shared devices found : {len(shared_devices)}")
    print(f"  Detected in          : {time.time() - t0:.2f}s")
    if shared_devices:
        sample_dev = next(iter(shared_devices))
        print(f"  Example: {sample_dev} -> {shared_devices[sample_dev][:4]}...")

    # 5. Precompute all account graph risks and save graph_risks.json
    print("\nPrecomputing graph risks for all nodes...")
    t0 = time.time()
    all_risks = precompute_all_risks(G, cycles, fan_in, shared_devices)
    print(f"  Computed in {time.time() - t0:.2f}s")

    # 6. Summary counts
    n_in_cycle    = sum(1 for r in all_risks.values() if r["in_cycle"])
    n_fan_in      = sum(1 for r in all_risks.values() if r["fan_in_flag"])
    n_shared_dev  = sum(1 for r in all_risks.values() if r["shared_device_flag"])
    n_any_risk    = sum(1 for r in all_risks.values() if r["graph_risk"] > 0)

    print("\n" + "=" * 60)
    print("GRAPH RISK SUMMARY")
    print("=" * 60)
    print(f"  Total nodes analysed   : {len(all_risks):,}")
    print(f"  Accounts in cycle      : {n_in_cycle}")
    print(f"  Accounts with fan-in   : {n_fan_in}")
    print(f"  Accounts shared device : {n_shared_dev}")
    print(f"  Accounts with any risk : {n_any_risk}")

    # 7. Assertions (scenarios planted in Phase 1 must be found)
    assert n_in_cycle   >= 1, "FAIL: No accounts found in_cycle — circular scenario missing!"
    assert n_fan_in     >= 1, "FAIL: No fan-in accounts found — mule scenario missing!"
    assert n_shared_dev >= 1, "FAIL: No shared-device accounts found — ATO/mule scenario missing!"

    print("\n[OK] in_cycle      >= 1  (PASSED)")
    print("[OK] fan_in_flag   >= 1  (PASSED)")
    print("[OK] shared_device >= 1  (PASSED)")

    # 8. Neighbourhood smoke test
    sample_account = next(iter(G.nodes()))
    hood = get_neighborhood(sample_account, G, max_hops=2, max_nodes=100)
    print(f"\nNeighbourhood of '{sample_account}': "
          f"{len(hood['nodes'])} nodes, {len(hood['edges'])} edges, "
          f"truncated={hood['truncated']}")

    print("\n" + "=" * 60)
    print("Graph analysis complete. Artifacts saved.")
    print("=" * 60)
