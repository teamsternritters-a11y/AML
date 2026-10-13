# DEMO.md — Synesis 26 Presentation Script

> **Duration:** 2 minutes  
> **Format:** Live dashboard walkthrough  
> **Audience:** Judges / technical reviewers  

---

## Spoken Script

| Time | Action | Spoken Script |
|------|--------|---------------|
| **0:00 – 0:20** | Introduce the problem and synthetic environment. | "Digital payments scale fast, but so do coordinated fraud rings. Simple rules often miss these patterns and create false positives. We built a synthetic environment to orchestrate a better response." |
| **0:20 – 0:45** | Show live feed and select a suspicious payment. | "Here is our live feed. Notice how the engine doesn't just flag it—it routes it. The score you see combines an ML probability, account graph signals, and velocity rules." |
| **0:45 – 1:10** | Open the explanation and graph neighbourhood. | "Explainability is key. SHAP values tell us *why* the ML flagged it—like an unusual amount spike. And our graph detects if the account is part of a circular transfer or shares a burner device." |
| **1:10 – 1:30** | Open a case and record a reviewer decision. | "For high-risk items, we don't just block; we create a review case. An analyst can inspect the evidence here and record a final decision, keeping a clean audit trail." |
| **1:30 – 1:50** | Show rules-only vs hybrid metrics. | "Looking at our metrics, our hybrid approach drastically cuts the false-positive rate compared to a rules-only baseline, while maintaining sub-100 millisecond latency." |
| **1:50 – 2:00** | State limitations and next steps. | "Of course, this is built on synthetic data, so results are a prototype heuristic. Real-world validation is the next step. Thank you." |

---

## Key Stats to Quote (from `backend/generated/metrics.json`)

| Stat | Value |
|------|-------|
| FPR — Rules baseline | **13.29 %** |
| FPR — ML hybrid | **2.36 %** |
| FPR reduction | **82 %** |
| ML Precision | **0.509** (vs 0.253 rules-only) |
| Median API latency | **7.52 ms** |
| p95 API latency | **8.23 ms** |
| Test dataset size | **15,000 rows** |
| Fraud prevalence | **6.1 %** |

---

## Dashboard Navigation Cheat Sheet

| Slide | Page | URL |
|-------|------|-----|
| Live feed | Live Feed | `http://localhost:5173/` |
| Suspicious account network | Graph Explorer | `http://localhost:5173/graph` |
| Compliance review | Case Queue | `http://localhost:5173/cases` |
| Performance summary | Metrics | `http://localhost:5173/metrics` |

---

## Demo Tips

- **Before presenting:** Click **"Simulate Transaction"** 5–6 times on the Live Feed page to populate the stream with a mix of ALLOW, OTP, HOLD, and BLOCK transactions.
- **Selecting a BLOCK transaction** and clicking **"Inspect"** will open the Investigation Drawer with SHAP reasons and graph signals.
- **Graph Explorer:** Type `ACC0445` to see a known money-mule ring with `in_cycle=True`, `fan_in_flag=True`, `shared_device_flag=True`.
- **Case Queue:** Open any BLOCK case and use the **"Confirm Fraud"** or **"Clear — False Positive"** buttons to demonstrate the audit trail.
- If asked about latency: the median is **7.52 ms**; the high mean (75.91 ms) is warm-up noise from the first request.
