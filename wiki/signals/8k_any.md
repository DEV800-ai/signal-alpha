---
signal_id: 8k_any
status: graveyard
hold_days: 30
data_sources:
  - db:sec_filings
  - db:prices
validated_run_id: 5
code_version: b93c6f1
event_max_date: 2024-12-30
lifecycle: draft
last_updated: 2026-05-05
last_reviewed: 2026-05-05
freshness_status: current
confidence: low
schema_version: 1
---

# 8K Any

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #5](signal_run:5) — 2026-05-03

- N events: **4956** (window 2018-01-02 → 2024-12-30)
- Hit rate: **55.4%**
- Mean return: **+1.95%** over 30 trading days
- Mean alpha vs sector: **+0.34%**
- p-value vs sector: **0.1004** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.34**
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

- 2026-05-03 — run_id=5 completed. [Results](signal_run:5). Status: graveyard.
