---
signal_id: 8k_excl_earnings__holdout_30d
status: graveyard
hold_days: 30
data_sources:
  - db:earnings_events
  - db:prices
validated_run_id: 24
code_version: b1cd06c
event_max_date: 2026-03-18
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: low
schema_version: 1
---

# 8K Excl Earnings  Holdout 30D

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #24](signal_run:24) — 2026-05-06

- N events: **722** (window 2025-01-06 → 2026-03-18)
- Hit rate: **59.7%**
- Mean return: **+6.00%** over 30 trading days
- Mean alpha vs sector: **+0.76%**
- p-value vs sector: **0.2708** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.86**
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

- 2026-05-06 — run_id=24 completed. [Results](signal_run:24). Status: graveyard.
