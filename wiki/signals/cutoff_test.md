---
signal_id: cutoff_test
status: graveyard
hold_days: 30
data_sources:
  - db:prices
validated_run_id: 1
code_version: b93c6f1
event_max_date: 2024-06-01
lifecycle: draft
last_updated: 2026-05-05
last_reviewed: 2026-05-05
freshness_status: current
confidence: low
schema_version: 1
---

# Cutoff Test

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #1](signal_run:1) — 2026-05-03

- N events: **2** (window 2023-06-01 → 2024-06-01)
- Hit rate: **100.0%**
- Mean return: **+11.55%** over 30 trading days
- Mean alpha vs sector: **+4.20%**
- p-value vs sector: **0.4774** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **4.89**
- Max drawdown of sequential equity curve: **0.0%**
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

- 2026-05-03 — run_id=1 completed. [Results](signal_run:1). Status: graveyard.
