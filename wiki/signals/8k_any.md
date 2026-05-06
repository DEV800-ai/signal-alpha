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
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: low
schema_version: 1
---

# 8-K Filing — Any

## Definition

<!-- claim_type: factual_claim -->

Fires on every 8-K filing submitted to EDGAR by a company in the universe. Multiple 8-K filings by the same company on the same date are deduplicated to a single event. The backtest enters at the next trading day's open after the filing date (T+1), reflecting EDGAR's end-of-day convention for filing timestamps.

Parameters: `exclude_earnings=False`. Data source: `db:sec_filings`, form = `8-K`.

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

8-K filings disclose material events — agreements, leadership changes, financing, legal matters — that may not be immediately and fully priced in. The hypothesis is that the market underreacts to some subset of these disclosures, producing a drift over the following 30 days. However, the "any 8-K" version includes a large proportion of routine or low-materiality filings (e.g., departure of minor executives, routine amendments) which dilute the signal.

The alpha vs sector is +0.34% with p=0.10, just above the 0.05 bar. The direction is right but the noise from routine filings likely buries the true signal.

## Known limitations

<!-- claim_type: risk_note -->

- Graveyard status: p=0.10 vs sector, not statistically significant.
- Includes earnings-related 8-Ks (item 2.02), which have a different and potentially confounding return profile.
- High event volume (4,956) means many low-information filings dilute the edge. Filtering by item type is necessary — see [8-K Filing — Excluding Earnings](8k_excl_earnings.md) and [8-K Item 1.01](8k_item_1_01.md).
- EDGAR timestamps do not include intraday time — late-day filings and early-morning filings are both treated as T+1, creating some look-ahead slippage in edge cases.

## Comparable signals

<!-- claim_type: factual_claim -->

- [8-K Filing — Excluding Earnings](8k_excl_earnings.md) — same signal with item 2.02 (earnings) filings removed; stronger edge
- [8-K Item 1.01 — Material Agreement](8k_item_1_01.md) — narrowed to material contract signings only

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** benchmarking more specific 8-K variants — this is the baseline that all filtered versions should beat.
- **DO NOT use when:** making research conclusions. The unfiltered version is too noisy to produce a reliable edge. Use [8k_excl_earnings](8k_excl_earnings.md) or [8k_item_1_01](8k_item_1_01.md) instead.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=5 completed. [Results](signal_run:5). Status: graveyard. p=0.10 vs sector.
