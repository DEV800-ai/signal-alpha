---
signal_id: volume_anomaly_5_60_t2.0__holdout_10d
status: borderline
hold_days: 10
data_sources:
  - db:prices
validated_run_id: 23
code_version: b1cd06c
event_max_date: 2026-04-14
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly 5 60 T2 0  Holdout 10D

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #23](signal_run:23) — 2026-05-06

- N events: **296** (window 2025-01-08 → 2026-04-14)
- Hit rate: **62.2%**
- Mean return: **+3.07%** over 10 trading days
- Mean alpha vs sector: **+1.24%**
- p-value vs sector: **0.0657** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **1.23**
- Max drawdown of sequential equity curve: **-92.3%**
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

- 2026-05-06 — run_id=23 completed. [Results](signal_run:23). Status: borderline.
