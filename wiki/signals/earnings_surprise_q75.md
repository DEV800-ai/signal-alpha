---
signal_id: earnings_surprise_q75
status: graveyard
hold_days: 60
data_sources:
  - db:earnings_events
  - db:prices
validated_run_id: 4
code_version: b93c6f1
event_max_date: 2024-12-04
lifecycle: draft
last_updated: 2026-05-05
last_reviewed: 2026-05-05
freshness_status: current
confidence: low
schema_version: 1
---

# Earnings Surprise Q75

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #3](signal_run:3) — 2026-05-03

- N events: **410** (window 2018-01-16 → 2024-12-04)
- Hit rate: **52.0%**
- Mean return: **+1.55%** over 30 trading days
- Mean alpha vs sector: **-0.34%**
- p-value vs sector: **0.7055** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.23**
- Max drawdown of sequential equity curve: **-99.3%**

[Run #4](signal_run:4) — 2026-05-03

- N events: **410** (window 2018-01-16 → 2024-12-04)
- Hit rate: **58.0%**
- Mean return: **+4.96%** over 60 trading days
- Mean alpha vs sector: **+1.13%**
- p-value vs sector: **0.4594** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.31**
- Max drawdown of sequential equity curve: **-99.9%**
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

- 2026-05-03 — run_id=3 completed. [Results](signal_run:3). Status: graveyard.
- 2026-05-03 — run_id=4 completed. [Results](signal_run:4). Status: graveyard.
