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
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly — 5/60-day, Threshold ×2.0

## Definition

<!-- claim_type: factual_claim -->

Fires when a stock's 5-day average daily volume exceeds its 60-day average daily volume by more than 2.0 standard deviations. Events are debounced with a 5-day cooldown so that a single sustained surge does not produce multiple firings. Data source: daily OHLCV prices from `db:prices`.

Parameters: `window_short=5`, `window_long=60`, `threshold=2.0`, `debounce_days=5`.

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

Unusual volume relative to recent history often reflects institutional activity — accumulation ahead of a catalyst or distribution after one. A 2-sigma surge above the 60-day baseline suggests participation well outside normal trading patterns. If the surge is driven by informed buying, price should continue to drift upward over the following 30 days as the market processes the new information. The 5/60-day ratio captures short-term spikes without confusing them with structural increases in average volume over time.

## Known limitations

<!-- claim_type: risk_note -->

- Volume surges also occur on earnings days and 8-K filing days, where the return profile is driven by the event rather than the volume itself. This signal does not exclude those dates, so some events overlap with the earnings and 8-K signals.
- The 60-day rolling baseline shifts slowly after a regime change in a stock's trading activity (e.g., after inclusion in an index), potentially suppressing signals during the adjustment period.
- Max drawdown of the sequential equity curve is -100%, indicating the signal can produce extended losing streaks. It should not be traded mechanically without position sizing discipline.
- Universe limited to `ai_infra` and adjacent sectors — behavior on broader universes is unknown.

## Comparable signals

<!-- claim_type: factual_claim -->

- [8-K Filing — Excluding Earnings](8k_excl_earnings.md) — captures the same non-earnings activity through the filing channel rather than volume
- [8-K Item 1.01 — Material Agreement](8k_item_1_01.md) — more specific subset of filing-driven volume events

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** looking for a broad, price-data-only signal that requires no fundamental data. Useful as a baseline or complement to filing-based signals.
- **DO NOT use when:** a ticker has recently had a structural change in average volume (index inclusion, ETF creation). Also avoid treating this as a standalone entry signal — the Sharpe of 0.35 and -100% max drawdown require strict position sizing and diversification across many concurrent events.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=2 completed. [Results](signal_run:2). Status: validated.
