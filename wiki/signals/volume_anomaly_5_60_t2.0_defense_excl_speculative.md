---
signal_id: volume_anomaly_5_60_t2.0_defense_excl_speculative
status: graveyard
hold_days: 30
data_sources:
  - db:prices
validated_run_id: 10
code_version: f91d1d3
event_max_date: 2024-12-24
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: low
schema_version: 1
---

# Volume Anomaly 5 60 T2 0 Defense Excl Speculative

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #10](signal_run:10) — 2026-05-06

- N events: **279** (window 2018-04-03 → 2024-12-24)
- Hit rate: **53.4%**
- Mean return: **+0.32%** over 30 trading days
- Mean alpha vs sector: **-0.10%**
- p-value vs sector: **0.8740** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.07**
- Max drawdown of sequential equity curve: **-99.4%**
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

- 2026-05-06 — run_id=10 completed. [Results](signal_run:10). Status: graveyard.
