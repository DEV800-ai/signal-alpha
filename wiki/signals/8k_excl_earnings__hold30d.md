---
signal_id: 8k_excl_earnings__hold30d
status: borderline
hold_days: 30
data_sources:
  - db:earnings_events
  - db:prices
validated_run_id: 21
code_version: 8a75bd6
event_max_date: 2024-12-30
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# 8K Excl Earnings  Hold30D

## Definition

<!-- claim_type: factual_claim -->

_TODO: Describe the signal definition — what event fires, on what data, with what parameters._

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #21](signal_run:21) — 2026-05-06

- N events: **3754** (window 2018-01-02 → 2024-12-30)
- Hit rate: **56.2%**
- Mean return: **+2.12%** over 30 trading days
- Mean alpha vs sector: **+0.46%**
- p-value vs sector: **0.0529** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.37**
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

- 2026-05-06 — run_id=21 completed. [Results](signal_run:21). Status: borderline.
