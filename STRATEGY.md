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
| AI infrastructure | SOXX |
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
- **Hold:** validated per signal via hold-period sweep. Volume anomaly validated at 15 days (best p + Sharpe). 90 days for slow signals (patents, insider buying).
- **Stop loss:** 10% from entry.
- **Take profit:** none — let it run to time exit.

These are starting defaults. Tune them only after a signal has shown an edge under the default rule. Tuning rules first turns the tool into a curve-fit machine.

> **Note:** Position sizing is out of scope until signals stabilize. The dashboard surfaces signal firings; the user decides whether to act. No buy/sell recommendations are generated.

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
- FastAPI web dashboard (deployed on Railway) — replaced the markdown email format

## Phase 6 — Dashboard

The markdown daily report format was superseded by the FastAPI web dashboard. The dashboard provides:

- **Daily Brief** — validation status for every signal run (p-value, alpha, Sharpe, freshness)
- **Top 10** — ranked stock leaderboard with Long / Mid-term / Opportunity modes and a Blended ranking option
- **Wiki Editor** — browse and validate signal/company wiki pages
- **How It Works** — full methodology explainer

### Three-layer scoring (current)

Rankings pass through three compounding layers:

1. **Signal Score** — backtest edge: `alpha × hit_rate × log(N)`. Base layer; always applied.
2. **Human Quality** — four fundamentals checks (liquidity, trend, market alignment, EPS growth). Multiplier `0.75 + 0.25 × quality_score` applied to all score columns so quality-adjusted rankings reflect fundamentals confidence.
3. **Opportunity Potential** — six research-upside checks (valuation room, growth support, technical extension, market cap asymmetry, sector tailwind, risk penalty). Applied as a second multiplier `0.75 + 0.25 × opp_score` only when Rank by = **Blended**. Visible as a badge on every card regardless of mode.

### Research modal

Every stock has a **Research** button that opens a deterministic research pack: signal stats, quality checks, opportunity checks, wiki page freshness, recent Top 10 appearances, and a next-steps checklist. No LLM. No buy/sell language.

### Fundamentals pipeline

`ingest_fundamentals.py` fetches trailing P/E, forward P/E, P/B, trailing EPS, YoY + quarterly EPS growth, market cap, and revenue growth via yfinance on every scheduled run. Falls back to `income_stmt` Diluted EPS for tickers where yfinance doesn't carry `earningsGrowth` directly (e.g. GSAT, LITE).

The dashboard surfaces signal firings and historical statistics. It is opinionated on the **signal**, not on the trade. No buy/sell recommendations or position sizing suggestions are shown. The user decides whether to act.

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

## Execution plan — status

### Week 1 — Foundations ✅ DONE

- Universe: 68 tickers across 3 sectors, versioned with start dates.
- Prices: 2018–present daily OHLCV in DuckDB via yfinance (weekly auto-update).
- `backtest(events, hold_days)` implemented with all guardrails.

### Week 2 — First signals ✅ DONE

| Signal | Verdict | Notes |
|--------|---------|-------|
| volume_anomaly ×2.0 | ✅ VALIDATED | p=0.0046, alpha +1.27%, hold 15d |
| earnings_surprise q75 | ❌ GRAVEYARD | p=0.459 |
| 8k_excl_earnings | ❌ GRAVEYARD | p=0.053, failed holdout p=0.27 |
| insider_buy_100k | ❌ GRAVEYARD | p=0.918, sector alpha ~0 |

Hold-period sweep completed (5/10/15/20/30d). 15d is optimal.
Holdout validation completed on 2025–2026 data: volume anomaly held up (alpha +1.58%, Sharpe 1.22).
Dashboard deployed on Railway with weekly auto-update via GitHub Actions.

### Week 3 — Differentiator signal ✅ DONE

- Patent cluster signal validated: p=0.0001, alpha +1.53%, 45d hold, Telecom only
- SEC filing summarization: deferred (no active need while signal pipeline is active)

### Phase 6 extension — Intelligence layers ✅ DONE

- **Fundamentals ingestion** — yfinance pipeline for P/E, P/B, EPS growth, market cap, revenue growth; income statement fallback for missing earningsGrowth
- **Human Quality layer** — 4-check quality score applied as a multiplier to all signal scores
- **Opportunity Potential layer** — 6-check research upside score; shown as badge on all cards; used as a second multiplier in Blended ranking mode
- **Research modal** — deterministic per-ticker research pack (signal stats, quality, opportunity, wiki context, next steps); no LLM
- **Blended ranking** — Signal × Quality × Opportunity composite; selectable via "Rank by" dropdown
- **159 tests** covering ranking, quality checks, opportunity checks, and research pack assembly

### Week 4 — Out-of-sample ✅ DONE (pulled forward)

- Holdout run on 2025+ data completed (run_ids 22–24).
- volume_anomaly passed holdout. 8k_excl_earnings failed.
- Signal graveyard maintained in wiki.

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
