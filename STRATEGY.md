# SignalAlpha — Strategy v3

## Purpose

A personal research engine that detects early signals in three sectors (AI infrastructure, Space/Defense, Telecom) and validates whether those signals historically lead to returns *before* any capital is committed.

The system does **not** predict prices. It surfaces statistically validated setups; the user decides what to do with them.

## Core principles (load-bearing)

1. **Validation before features.** No signal goes into production until it passes the methodology in Phase 3.
2. **Point-in-time data only.** Every signal must be reconstructable as of its event date. No today-snapshots labeling past events.
3. **Sector-relative benchmarks, not SPY alone.** Every backtest reports performance against the relevant sector ETF.
4. **Expected value over hit rate.** A signal is judged by mean return and tail behavior, not just by how often it "wins."
5. **Out-of-sample holdout.** 2025 is reserved. Touched once per signal at the end of iteration. Never used to tune.
6. **Manual until painful.** Automate when the manual version starts costing real time, not before.

## Universe

~60–90 stocks total, ~25–30 per sector. Fixed and recorded with start dates so survivorship bias can be audited.

- **AI infrastructure:** NVIDIA, AMD, Broadcom, Intel, Cisco, Microsoft, Marvell, Arista, Super Micro, Dell, etc.
- **Space / Defense:** Rocket Lab, Lockheed Martin, Northrop Grumman, L3Harris, RTX, Boeing, etc.
- **Telecom:** Cisco, Ericsson, Nokia, Qualcomm, T-Mobile, Verizon, AT&T, etc.

**Survivorship handling.** For backtests that ask "would this signal have picked the winners," expand the universe to all sector constituents above a market-cap floor *as of the test window's start*, including delisted/acquired names.

## Sector benchmarks

| Sector | Benchmark |
| --- | --- |
| AI infrastructure | SOXX (semis) + IGV (software) |
| Space / Defense | ITA |
| Telecom | IYZ |
| Broad baseline | SPY |

A signal must beat the relevant sector ETF on a risk-adjusted basis to be useful. Beating SPY alone is not sufficient — most of these names beat SPY in any bull tape.

## Signal specification format

Every signal is defined with these fields. If a candidate cannot be expressed this way, it is not yet a signal.

| Field | Example |
| --- | --- |
| Name | `8k_item_1_01_material_agreement` |
| Data source | SEC EDGAR full-text + filing metadata |
| Event trigger | 8-K filed with Item 1.01 |
| Measurement | Date of filing, ticker, item code |
| Threshold | None (event-based) |
| Hold period | 30 days, 90 days |
| Cost | Free |

## Starter signal set (Week 2)

These come first because the data is free, the events are well-defined, and there is academic precedent so the backtest framework can be calibrated against known effects.

1. **Earnings surprise.** EPS actual vs. consensus, T+1 to T+30 reaction.
2. **8-K event presence.** Any 8-K filing, refined by item type (1.01 material agreement, 2.02 results, 5.02 leadership change).
3. **Insider buying — Form 4.** Open-market purchases by officers/directors above a $ threshold.
4. **Volume anomaly without news.** 5-day volume > 2× 60-day median, with no 8-K or earnings within 3 days.
5. **Patent grant cluster.** USPTO PatentsView: ≥5 grants assigned to a sector ticker within a rolling 30-day window.

Signals 1–4 are well-studied — they are the calibration set. If the backtest framework can't reproduce known effects on them, the framework is broken, not the signals. Signal 5 is the differentiator candidate.

**Deferred to month 2:** CAPEX growth, GPU demand proxies, hiring spikes, news-spike NLP. All require paid data, ToS-questionable scraping, or NLP work that should not happen before signals 1–5 are validated.

## Phase 3 — Backtesting (the load-bearing phase)

### Framework first, signals second

Before any signal is implemented, build a single function:

```python
backtest(events: DataFrame, hold_days: int) -> Result
```

`events` has columns: `ticker, event_date, signal_name`.
`Result` returns: hit rate, mean return, median return, std, Sharpe, max drawdown, return vs. sector ETF, return vs. SPY, sample size, and p-value vs. zero-mean null.

Every signal then becomes one DataFrame away from a verdict.

### Methodology guardrails

- **Point-in-time prices.** Adjusted close, but fetched as of event date. No look-ahead on splits, dividends, or constituents.
- **No data leakage.** If a signal uses revisions or restatements, only use the version available at event date.
- **Realistic execution.** Entry at next-day open, not event-day close. Round-trip slippage assumption: 10 bps.
- **Multiple-testing.** 2025 is held out. While iterating on 2018–2024, treat any single great-looking result with skepticism — try it on a different sector before celebrating.
- **Sample-size floor.** Don't report results for fewer than 30 events.
- **Statistical significance.** Report p-value vs. zero-return null and CI on mean return. 65% hit rate over 20 events is not significant. Over 200 events it is.

### What "validated" means

A signal goes into production only if:

- N ≥ 30 events in 2018–2024
- Mean return beats the sector ETF with p < 0.05
- The result holds in the 2025 holdout when finally checked

Signals that fail go to the **signal graveyard** — a dated log — so they aren't unconsciously retried.

## Phase 4 — Position sizing and exit rules

Even a personal tool needs a closed loop. Defaults:

- **Position size:** 2% of capital per signal firing. Max 10% per ticker across signals.
- **Hold:** 30 days for fast signals (earnings, 8-K, volume), 90 days for slow signals (patents, insider buying).
- **Stop loss:** 10% from entry.
- **Take profit:** none — let it run to time exit.

These are starting defaults. Tune them only after a signal has shown an edge under the default rule. Tuning rules first turns the tool into a curve-fit machine.

## Phase 5 — Pipeline

```
EDGAR / yfinance / USPTO  →  raw tables (DuckDB)
                           →  event tables (one per signal)
                           →  backtest()  →  validated signal registry
                           →  daily scan  →  daily report
```

**Stack:**

- Python, DuckDB, pandas/Polars
- `yfinance` for prices, `sec-edgar-downloader` for filings, USPTO PatentsView API for patents
- Claude API for filing summarization only, cached aggressively
- Streamlit or markdown email for the daily report — no web app

## Phase 6 — Daily report format

```
Date: 2026-05-03
Universe scanned: 87 tickers
Signals fired today: 2

INTC — 8-K Item 1.01 (material agreement)
  Signal stats (2018–2024): N=312, mean 30d return +1.8%,
                            vs SOXX +0.4%, p=0.02
  Suggested: 2% position, 30-day hold, 10% stop

RKLB — Insider buy, Form 4, $480k
  Signal stats (2018–2024): N=44, mean 90d return +6.1%,
                            vs ITA +1.2%, p=0.04
  Suggested: 2% position, 90-day hold, 10% stop
```

The report is opinionated on the **signal**, not on the trade. The user decides whether to act.

## Phase 7 — Cost control

- Claude API used only for natural-language filing summaries, cached by filing ID. Same filing is never summarized twice.
- No daily recomputation of historical data — only incremental updates.
- Patent and EDGAR pulls nightly, not real-time.
- Estimated steady-state cost: < $20/month.

## Phase 8 — Telegram (deferred)

Out of scope until signals 1–5 are validated. If/when added:

- Public channels via official Bot API only.
- Used as **secondary confirmation**, never primary.
- Validated through the same backtest framework as everything else.

## Phase 9 — Private → Public mapping (deferred to v2)

The "Stoke Space → Rocket Lab" idea is the most interesting potential differentiator but has no committed data source. Options:

- Crunchbase API (limited free tier, patchy data)
- Manual log of private-market reads, mapped to public exposure
- PitchBook (paid, expensive)

**Decision deferred** until signals 1–5 are validated. Until then, a manual notes file is enough.

## 4-week execution plan (revised)

### Week 1 — Foundations

- Define the universe (60–90 tickers) and write it to a versioned table with start dates.
- Pull 2018–2025 daily prices for the universe + benchmark ETFs into DuckDB.
- Implement `backtest(events, hold_days)` with all guardrails above.
- **Smoke test:** feed it post-earnings-announcement drift events and verify results match published academic numbers. If they don't, the framework is broken — fix before moving on.

### Week 2 — First signals

- Implement signals 1–4 (earnings, 8-K, insider buying, volume anomaly).
- Run on 2018–2024. Record results in the signal registry.
- Kill any that fail the validation bar. Do not tune them yet.

### Week 3 — Sector signal + summarization

- Implement signal 5 (patent grants).
- Add SEC filing summarization (Claude API, cached).
- First end-to-end run: nightly job → event tables → daily report.

### Week 4 — Out-of-sample and reporting

- Run validated signals on 2025 holdout. Record the result. Do not tune.
- Polish the daily report (markdown or Streamlit).
- Write signal-graveyard entries for everything that died.

## What changed from v2

- Backtest methodology specified in detail (survivorship, look-ahead, baselines, sample size, significance).
- Signal definitions converted from categories to a strict, codeable format with concrete examples.
- Starter signal set is concrete, prioritized, and chosen so the framework can be calibrated against known academic effects.
- Position sizing and exit rules added — closes the loop from "signal" to "trade."
- Phase 9 (private→public) honestly labeled deferred without a data source.
- Week 1 dedicated to the backtest framework, not signals.
- Out-of-sample holdout policy made explicit.
- Signal graveyard introduced.

## Out of scope (deliberately)

- UI beyond markdown/Streamlit
- Multi-user features
- Real-time streaming
- Options-specific signals (IV, unusual options activity) — different system, different data
- Macro overlays
- Anything requiring paid data feeds
