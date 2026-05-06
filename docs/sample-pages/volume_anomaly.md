---
signal_id: volume_anomaly_5_60_t2.0
status: validated
hold_days: 30
data_sources:
  - db:prices
validated_run_id: 2
code_version: 5b6e8f1
event_max_date: 2024-12-31
lifecycle: validated
last_updated: 2026-05-05
last_reviewed: 2026-05-05
freshness_status: current
confidence: medium
schema_version: 1
---

# volume_anomaly (5/60, threshold 2.0)

## Definition

<!-- claim_type: factual_claim -->

Event: a `(ticker, date)` where the 5-day mean trading volume divided by the
60-day median trading volume exceeds 2.0, and at least 5 calendar days have
passed since the previous firing on that ticker (debounce).

- Inputs: `prices.volume` (DuckDB)
- Output: events DataFrame with columns `ticker, event_date, ratio`
- Implementation: `src/signalalpha/signals/volume_anomaly.py::detect` (pinned by `code_version` frontmatter)

The output is fed to `backtest()` with `hold_days=30`, no slippage adjustment
beyond the default 10 bps, and the universe defined in `data/universe.csv`.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #2](signal_run:2) — 2026-05-03

- N events: **1480** (window 2018-03-28 → 2024-12-24, 2025 held out)
- Hit rate: **54.4%**
- Mean return: **+3.14%** over 30 trading days
- Mean alpha vs SOXX/ITA/IYZ (per event): **+1.37%**
- p-value vs sector: **0.0308** — below the 0.05 bar — **VALIDATED**
- Sharpe (annualized): **0.35**
- Max drawdown of sequential equity curve: **-100%** (signal would not be sized
  all-in in practice)

<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

A sudden 2x rise in 5-day volume against a 60-day baseline is consistent with
new information arriving — earnings leaks, contract awards, sector-rotation
flows, or institutional accumulation — that is not yet fully reflected in
price. Holding 30 days lets the post-event drift play out without overlapping
into the next quarter's noise. The economic story is weakest on the
top-firing-rate names, where elevated volume is the regime, not the signal.

## Known limitations

<!-- claim_type: risk_note -->

- Top firing tickers skew to small/volatile names (SPCE, ASTS, GSAT, SATS).
  Performance on liquid megacaps may be weaker — stratified backtest pending.
- "No news within 3 days" filter is **not** applied yet; results may include
  earnings-driven volume that overlaps with the `earnings_surprise` signal.
- 60-day median can be skewed by extended high-volume regimes (e.g., a name
  that has been in the news for two months straight).
- Max drawdown of -100% on the sequential equity curve indicates the signal is
  **not** sized as a full-portfolio bet — sizing rules belong outside this page.

## Comparable signals

<!-- claim_type: factual_claim -->

- [`earnings_surprise_q75`](../signals/earnings_surprise_q75.md) (graveyard) —
  overlaps when volume spikes are earnings-driven.
- [`8k_excl_earnings`](../signals/8k_excl_earnings.md) (borderline) — overlaps
  when volume spikes coincide with material agreements.

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** a name in the universe shows a daily fire and no concurrent
  earnings event or 8-K within ±3 calendar days.
- **DO NOT use when:** the firing ticker is a top-firing-rate name (>50
  firings in the iteration window) — those are noise-prone.
- **DO NOT use when:** the firing date is within 1 trading day of an FOMC
  release or major sector ETF rebalance — sector-relative alpha is
  contaminated.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — created and validated. [run_id=2](signal_run:2). Curator: ip.
- 2026-05-03 — observed top-firing-tickers skew; flagged as limitation §4.
- 2026-05-05 — page drafted against `SIGNAL_SCHEMA v1`. No status change.
