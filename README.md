# SignalAlpha

A strategic research operating system for asymmetric, thematic, and transitional investing. It watches 68 stocks across AI, Space & Defense, and Telecom for repeating statistical patterns, then layers signal validation, quality checks, opportunity assessment, portfolio context, and strategic classification on top of every candidate.

> **This is not financial advice. No buy/sell recommendations are generated.**

---

## Live Dashboard

```bash
uv run python -m signalalpha.wiki.app
# Open http://127.0.0.1:8000
```

### Tabs

| Tab | Description |
|-----|-------------|
| **Top Research Candidates** | Ranked leaderboard with signal, quality, and opportunity overlays |
| **Portfolio Context** | Theme exposure, role/risk/conviction distribution across top 15 candidates |
| **Strategic View** | Candidates grouped by type: Asymmetric · Transitional · Compounder · Signal Play |
| **Wiki Editor** | Browse and validate wiki pages; run the auto-generator |
| **How It Works** | Plain-language explainer — what the numbers mean and how the system works |
| **Rotation Log** | History of stocks entering and exiting the top list |
| **Daily Brief** | Validation status for every signal run — p-value, alpha, Sharpe, context freshness |

### Top 10 — Investment Modes

**Long — 12 months+**
Stocks with strong historical indicators for long-term investors. Identifies stocks that consistently outperform their sector over time.
Ranked by: `alpha × hit_rate × log(N)`

**📈 Mid-term — 1 to 3 months**
Same signal, but ranks stocks that win consistently *and* with low volatility. Suitable for patient holds of 1–3 months.
Ranked by: `(alpha / volatility) × hit_rate × log(N)`

**💎 Opportunity — Buy the Dip**
Stocks with a proven positive edge that are currently trading *below* their 50-day moving average. The deeper the dip, the higher the score.
Ranked by: `composite_score × (1 + dip_pct × 3)`

Each stock shows a **risk badge** based on return volatility:
- 🟢 LOW — std < 10%
- 🟡 MED — std 10–20%
- 🔴 HIGH — std > 20%

**Rank by dropdown** — four options:
| Option | Formula |
|--------|---------|
| Composite | `alpha × hit_rate × log(N)` |
| Avg alpha vs sector | raw alpha |
| Hit rate | raw win % |
| **Blended** | Composite × Quality multiplier × Opportunity multiplier — the full three-layer score |

**Filters available:** signal quality (validated / borderline / all), sector, ranking method, and recency (only shows stocks where the signal fired in the last 90 days by default).

**TA Overlay (optional):** toggle the 📊 button to add RSI(14), 50-day MA, and 200-day MA on each card as a secondary context layer.

---

## Five-Layer Context

Every candidate passes through five compounding layers of analysis:

### Layer 1 — Signal Score (the base)
Pure backtest edge: `alpha × hit_rate × log(N)`. Only validated signals (p < 0.05) shown by default.

### Layer 2 — Human Quality (always applied)
Adjusts the signal score by a multiplier based on four fundamentals checks:

| Check | What it looks at |
|-------|-----------------|
| **Liquidity** | Average daily volume ≥ 500k shares |
| **Trend** | Price above 50d and 200d moving average |
| **Market Alignment** | SPY above its 200d MA (broad market health) |
| **EPS Growth** | YoY earnings growth from fundamentals |

Multiplier: `0.75 + 0.25 × quality_score` — range is 0.875–1.0. A stock with bad fundamentals is ranked slightly lower; perfect quality is a small boost. The signal itself still dominates.

### Layer 3 — Opportunity Potential
Six-check assessment of *research upside* — how much room the stock still has to run. Applied on top of Layer 2 when Rank by = Blended.

| Check | What it measures | Weight |
|-------|-----------------|--------|
| **Valuation Room** | P/E or P/B vs sector norms | 20% |
| **Growth Support** | EPS growth + revenue growth | 20% |
| **Technical Extension** | How far above SMA50/SMA200/12m return | 25% |
| **Market Cap Asymmetry** | Small/mid caps have more room to move | 15% |
| **Sector Tailwind** | Forward-looking sector momentum | 10% |
| **Risk Penalty** | Quality layer fail/warn flags | 10% |

Each check returns pass / warn / unknown / fail. Weighted score → status: **high** (≥0.75), **medium** (0.45–0.75), **low** (<0.45), or **unknown** (≥4 unknowns).

Blended multiplier: `0.75 + 0.25 × opportunity_score` — applied after the quality multiplier, then re-sorted.

The Opportunity badge is visible on every card and in the leaderboard regardless of which ranking mode is active.

### Layer 4 — Portfolio Context
Soft heuristics that frame how a candidate fits into a broader portfolio thesis. Returns: **role** (Core / Growth / Speculative / Watchlist), **risk bucket** (Low / Medium / High), **conviction** (High / Medium / Low + reason), **themes**, and **exposure profile**. Visible in the research modal and the **Portfolio Context** tab.

### Layer 5 — Strategic Classification
Classifies what *type* of research opportunity each candidate represents:

| Type | What it means |
|------|--------------|
| **Asymmetric** | Small/mid-cap, high uncertainty, high optionality — pre-profitability or emerging theme |
| **Transitional** | Company changing regime — turnaround, business model shift, or sector rerating |
| **Compounder** | Large-cap with durable recurring economics and consistent capital return |
| **Signal Play** | Validated signal that doesn't fit neatly into the other three categories yet |

Visible in the **Strategic View** tab.

---

## Research Modal

Click the **Research** button on any stock to open a full research pack — built deterministically from existing data, no LLM, no buy/sell language.

Sections:
- **Signal Stats** — best signal for this ticker: alpha, hit rate, n events, p-value, validated/borderline/exploratory status
- **Human Quality** — the four quality checks with pass/warn/fail badges
- **Opportunity Potential** — all six opportunity checks with scores and status
- **Company Context** — wiki page existence, freshness (current/stale/missing), last reviewed date
- **Recent Appearances** — last 10 times this stock appeared in the Top 10
- **Next Steps** — deterministic checklist of what to investigate next, derived from data state

---

## How It Works

```
Detect → Backtest → Validate → Holdout → Live Re-run (every 3 days)
```

1. **Detect** — scan price/volume/patent data for candidate events (e.g. volume 2× the 60-day average)
2. **Backtest** — entry at T+1 open, hold N trading days, exit at open; deduct 10 bps slippage
3. **Validate** — paired t-test comparing stock return vs sector ETF; p < 0.05 required to be "validated"
4. **Holdout** — one-time test on reserved 2025+ data the system never trained on; results are final
5. **Live re-run** — every 3 days, fresh prices and fundamentals are pulled and signals re-checked

---

## Validated Signals

| Signal | Hold | Events | Alpha | p-value | Notes |
|--------|------|--------|-------|---------|-------|
| Volume Anomaly ×2.0 — 15d hold ★ | 15d | 1,480 | +1.27% | 0.0046 | Holdout: +1.58%, Sharpe 1.22 |
| Volume Anomaly ×2.0 — 10d hold | 10d | 1,480 | +1.10% | 0.0061 | Holdout: +1.24% |
| Volume Anomaly ×2.0 — 20d hold | 20d | 1,480 | +1.42% | 0.0062 | |
| Patent Cluster — Telecom, 45d hold ★ | 45d | 810 | +1.53% | 0.0001 | Telecom only (QCOM, IDCC, ERIC…) |

**Volume Anomaly** — fires when a ticker's 5-day average volume exceeds 2× its 60-day median. Fires across all three sectors.

**Patent Cluster** — fires when a telecom company receives ≥5 patent grants in any rolling 30-day window. Telecom companies are IP-licensing businesses; patent bursts signal upcoming licensing revenue that takes ~45 days to price in. Data: PatentsView S3 bulk files, updated monthly.

**Graveyard:** 8-K excl. earnings (failed holdout p=0.27), earnings surprise Q75, sector-scoped volume variants.

---

## Universe

68 public companies across three sectors:

| Sector | Benchmark ETF | Examples |
|--------|--------------|---------|
| AI Infrastructure | SOXX | NVDA, AMD, MSFT, PLTR, SMCI |
| Space & Defense | ITA | LMT, NOC, RTX, KTOS, RKLB |
| Telecom | IYZ | TMUS, VZ, QCOM, IDCC, ERIC |

---

## Key Metrics

| Metric | Plain English |
|--------|--------------|
| **Alpha vs Sector** | How much the stock beat its sector ETF — the main signal of edge |
| **Hit Rate** | % of past signal firings that ended in profit (>55% = good for longs) |
| **Avg Return** | Average gain per trade after transaction costs |
| **p-value** | Probability the alpha is due to luck (<0.05 = validated, >0.10 = graveyard) |
| **Composite Score** | `alpha × hit_rate × log(N)` — rewards alpha + consistency + history |
| **Mid-term Score** | `(alpha / volatility) × hit_rate × log(N)` — rewards steady gains |
| **Opportunity Score** | `composite × (1 + dip_pct × 3)` — boosts stocks below their 50d MA |
| **Quality Score** | Weighted average of 4 quality checks (0–1) |
| **Opportunity Potential** | Weighted average of 6 research-upside checks (0–1) |
| **Blended Score** | Signal × Quality multiplier × Opportunity multiplier |
| **Risk Level** | LOW / MED / HIGH based on how much individual trade returns vary |

---

## Automation

- **Ingest + signals:** GitHub Actions runs every 3 days, triggers Railway to pull fresh prices, fundamentals, and re-run all signals
- **Fundamentals:** yfinance fetches trailing P/E, forward P/E, P/B, trailing EPS, EPS growth (YoY + quarterly), market cap, revenue growth for every universe ticker; falls back to income statement Diluted EPS when yfinance doesn't carry earningsGrowth directly
- **Rotation log:** after each ingest, a snapshot of the Top 10 is saved; changes (entered / exited / rank moved) are recorded
- **Failure alerts:** email sent to the configured address if the scheduled job fails
- **Admin security:** all admin endpoints require `Authorization: Bearer <secret>` — the secret never appears in URLs or logs

---

## How to Run Locally

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run python -m signalalpha.wiki.app        # → http://127.0.0.1:8000
uv run python -m signalalpha.ingest_prices
uv run python -m signalalpha.ingest_fundamentals
uv run python scripts/run_signal_patent_telecom.py
uv run python -m signalalpha.wiki.autogen
```

---

## Project Structure

```
src/signalalpha/
  signals/                    # Signal detectors (volume_anomaly, patent_cluster …)
  quality/
    human_quality.py          # Layer 2 — 4-check quality scoring (liquidity, trend, market, EPS)
  opportunity/
    opportunity_potential.py  # Layer 3 — 6-check research upside scoring
  portfolio/
    portfolio_context.py      # Layer 4 — role, risk, conviction, themes, exposure
  classification/
    strategic_classification.py  # Layer 5 — Asymmetric / Transitional / Compounder / Signal Play
  wiki/
    app.py                    # FastAPI web UI (dashboard + API endpoints)
    admin.py                  # Admin endpoints (ingest, snapshot, restore-db) + rotation logic
    ranking.py                # Ranking SQL + scoring formulas (no FastAPI dependency)
    research.py               # GET /api/research/{ticker} — deterministic research pack builder
    autogen.py                # Wiki page scaffolder + AUTOGEN section updater
    brief.py                  # Daily brief builder
    validate.py               # Wiki page validator
  live_signals.py             # Runs all validated signals on current data
  ingest_prices.py            # Price ingestion (yfinance)
  ingest_fundamentals.py      # Fundamentals ingestion (yfinance: P/E, EPS, market cap, …)
  ingest_patents.py           # Patent ingestion (PatentsView S3 bulk files)
  db.py                       # DuckDB connection + schema (auto-migrates on connect)
scripts/                      # One-off research scripts (backtests, sweeps, holdout)
tests/                        # Pytest suite — 244 tests across all layers
wiki/                         # Research pages (signals, companies, sectors)
.github/workflows/            # Scheduled ingest job (every 3 days) with failure email
```

---

## Disclaimer

SignalAlpha surfaces historical statistical patterns only. Past edge does not guarantee future results. All results are backtested and may not reflect live trading conditions. Nothing here constitutes investment advice.
