---
signal_id: volume_anomaly_5_60_t2.0__hold10d
status: validated
hold_days: 10
data_sources:
  - db:prices
validated_run_id: 13
code_version: 8a75bd6
event_max_date: 2024-12-24
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly 5 60 T2 0  Hold10D

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #13](signal_run:13) — 2026-05-06

- N events: **1480** (window 2018-03-28 → 2024-12-24)
- Hit rate: **53.0%**
- Mean return: **+1.62%** over 10 trading days
- Mean alpha vs sector: **+1.10%**
- p-value vs sector: **0.0061** — below the 0.05 bar — **VALIDATED**
- Sharpe (annualized): **0.50**
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

- 2026-05-06 — run_id=13 completed. [Results](signal_run:13). Status: validated.
