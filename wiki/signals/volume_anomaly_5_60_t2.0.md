---
signal_id: volume_anomaly_5_60_t2.0
status: validated
hold_days: 30
data_sources:
  - db:prices
validated_run_id: 2
code_version: b93c6f1
event_max_date: 2024-12-24
lifecycle: draft
last_updated: 2026-05-05
last_reviewed: 2026-05-05
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly 5 60 T2 0

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #2](signal_run:2) — 2026-05-03

- N events: **1480** (window 2018-03-28 → 2024-12-24)
- Hit rate: **54.4%**
- Mean return: **+3.14%** over 30 trading days
- Mean alpha vs sector: **+1.37%**
- p-value vs sector: **0.0308** — below the 0.05 bar — **VALIDATED**
- Sharpe (annualized): **0.35**
- Max drawdown of sequential equity curve: **-100.0%**
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

_TODO: Describe the economic intuition behind why this signal should have predictive power._

## Known limitations

<!-- claim_type: risk_note -->

- _TODO: List known limitations, data gaps, or conditions where signal is unreliable._

## Comparable signals

<!-- claim_type: factual_claim -->

- _TODO: Link to related signals in the wiki._

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** _TODO_
- **DO NOT use when:** _TODO_

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=2 completed. [Results](signal_run:2). Status: validated.
