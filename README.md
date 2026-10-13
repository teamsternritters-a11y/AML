# SENTRIX · Real-Time Fraud & AML Risk Orchestration

> A prototype hybrid risk-scoring engine that processes financial transactions in real time,
> combining Machine Learning, Graph Analysis, and Business Rules — then surfaces results
> to compliance analysts through a live React dashboard.

---

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Generate synthetic data, train the ML model, and build the graph
python backend/data.py && python backend/train.py && python backend/graph.py

# 3. Start the FastAPI backend  (port 8000)
uvicorn backend.api:app --reload --port 8000

# 4. In a separate terminal — install and start the React frontend (port 5173)
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** in your browser.

---

## What It Does

SENTRIX is a real-time risk orchestration engine that scores every inbound payment using
three independent signals — a LightGBM ML model trained on behavioural features, a
NetworkX graph that detects circular transfers and shared-device syndicates, and a
deterministic rule layer that catches velocity spikes and new-device anomalies.
The three signals are fused into a single composite score (0–100) and routed to one of four
actions (ALLOW / OTP / HOLD / BLOCK). High-risk transactions are automatically escalated
into a compliance case queue where analysts can inspect SHAP-driven explanations, explore
the account's network neighbourhood, and record a final adjudication decision.

---

## Architecture

```
                         +---------------------------------------------+
  Synthetic /            |              RISK ENGINE                     |
  Live Payment  -------> |  +----------+  +-----------+  +---------+  |
  (POST /score)          |  | LightGBM |  |  NetworkX  |  |  Rules  |  |
                         |  |  ML Model|  |   Graph    |  |  Layer  |  |
  backend/data.py        |  |  (0.50 x)|  |  (0.30 x) |  | (0.20 x)|  |
  backend/features.py -> |  +----+-----+  +-----+-----+  +----+----+  |
  backend/train.py       |       |               |              |        |
  backend/graph.py       |       +---------------+--------------+        |
                         |                       |                        |
                         |            Composite Score  (0-100)            |
                         |           ALLOW / OTP / HOLD / BLOCK           |
                         +-------------------+-------------------------+
                                             |
                                    FastAPI (backend/api.py)
                                             |
                         +-------------------+-------------------------+
                         |               React Dashboard               |
                         |  Live Feed | Graph Explorer | Case Queue   |
                         |  Metrics   | Investigation Drawer          |
                         +---------------------------------------------+
```

Signal weights: **ML 50 % · Graph 30 % · Rules 20 %**

---

## Evaluation Metrics

All numbers are derived from `backend/generated/metrics.json` — no figures have been
fabricated. The ML metrics are evaluated on a held-out test split (15,000 rows,
6.1 % fraud prevalence). The latency figures are from the replay script (30 requests).

### Detection Performance

| Metric | Rules Baseline | ML Hybrid (threshold = 0.70) |
|---|---|---|
| **Precision** | 0.253 | **0.509** |
| **Recall** | 0.693 | 0.377 |
| **False-Positive Rate** | 13.29 % | **2.36 %** |
| True Positives | 634 | 345 |
| False Positives | 1,872 | 333 |
| True Negatives | 12,213 | 13,752 |
| False Negatives | 281 | 570 |

> The hybrid ML model reduces the **false-positive rate by 82 %** (13.29 % -> 2.36 %)
> compared to the rules-only baseline, at the cost of lower recall.
> In a real deployment the threshold would be tuned to balance FPR against recall.

### Latency (replay — 30 requests, single process)

| Metric | Value |
|---|---|
| Median latency | **7.52 ms** |
| p95 latency | **8.23 ms** |
| Mean latency | 75.91 ms |

> The high mean vs. median gap is caused by first-request model warm-up;
> steady-state throughput is well below the 100 ms SLA target.

---

## Project Layout

```
AML/
├── backend/
│   ├── data.py          # Synthetic transaction & account generation
│   ├── features.py      # Feature engineering (velocity, device, city flags)
│   ├── rules.py         # Deterministic rule engine
│   ├── train.py         # LightGBM training + SHAP explainer + artefact export
│   ├── graph.py         # NetworkX graph construction + risk tagging
│   ├── engine.py        # Composite scoring orchestrator
│   ├── api.py           # FastAPI REST endpoints
│   ├── replay.py        # Batch replay script for metrics generation
│   ├── models/          # fraud_model.joblib, model_metadata.json
│   └── generated/       # transactions.csv, accounts.csv, metrics.json, graph_risks.json
├── frontend/
│   ├── src/
│   │   ├── pages/       # LiveFeed, GraphExplorer, CaseQueue, Metrics
│   │   ├── components/  # MetricCard, RiskBadge, InvestigationDrawer, LoadingState
│   │   ├── hooks/       # useApi (polling), useCases
│   │   └── api/         # client.js (fetch wrapper with proxy)
│   └── vite.config.js
├── requirements.txt
├── README.md
└── DEMO.md
```

---

## API Reference (key endpoints)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/score` | Score a single transaction; returns action + SHAP reasons |
| `GET` | `/transactions` | Paginated scored transaction history |
| `GET` | `/cases` | Open compliance cases (HOLD/BLOCK) |
| `POST` | `/cases/{id}/decision` | Record analyst adjudication |
| `GET` | `/metrics` | Live performance metrics |
| `GET` | `/graph/{account_id}` | N-hop account network neighbourhood |

---

## Known Limitations

- All data is **synthetic**; planted patterns may not reflect real-world fraud.
- The weighted composite score is a **prototype heuristic**, not a calibrated probability.
- **Graph associations are signals, not proof of misconduct.**
- Latency figures depend on hardware and were measured locally on a single machine.
- This is **not a production AML compliance system** — it is a research prototype.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data generation | Python · Faker · NumPy |
| ML model | LightGBM · scikit-learn · SHAP |
| Graph analysis | NetworkX |
| Backend API | FastAPI · Uvicorn · Pydantic |
| Frontend | React 18 · Vite · Recharts · react-force-graph-2d |
| Persistence | In-memory (CSV + JSON artefacts) |
