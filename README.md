# SignalAlpha

A systematic signal research and ranking system. It watches 68 stocks across AI, Space & Defense, and Telecom for repeating patterns — unusual volume spikes, patent grant clusters — then goes back in history to measure what happened next. Only patterns that prove statistically significant are shown in the live dashboard.

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
| **Daily Brief** | Validation status for every signal run — p-value, alpha, Sharpe, context freshness |
| **Top 10** | Ranked stock leaderboard with three investment modes |
| **Rotation Log** | History of stocks entering and exiting the Top 10 |
| **Wiki Editor** | Browse and validate wiki pages; run the auto-generator |
| **How It Works** | Plain-language explainer — what the numbers mean and how the system works |

### Top 10 — Three Investment Modes

**▲ Long — 12 months+**
Stocks with strong historical indicators for long-term investors. The analysis identifies stocks that consistently outperform their sector over time — suited for buy-and-hold positions of 12 months or more.
Ranked by: `alpha × hit_rate × log(N)`

**📈 Mid-term — 1 to 3 months**
Same signal, but ranks stocks that win consistently *and* with low volatility. A stock that gains steadily beats one with the same average but wild swings. Suitable for patient holds of 1–3 months.
Ranked by: `(alpha / volatility) × hit_rate × log(N)`

**▼ Short — Up to 3 months**
Stocks with high potential for short-term gains of up to 3 months. When the volume spike pattern fires in these names it has historically led to rapid price moves — opportunities for active traders.
Ranked by: `|alpha| × (1 − hit_rate) × log(N)`

Each stock shows a **risk badge** based on return volatility:
- 🟢 LOW — std < 10%
- 🟡 MED — std 10–20%
- 🔴 HIGH — std > 20%

**Filters available:** signal quality (validated / borderline / all), sector, ranking method, and recency (only shows stocks where the signal fired in the last 90 days by default).

**TA Overlay (optional):** toggle the 📊 button to add RSI(14), 50-day MA, and 200-day MA on each card as a secondary context layer.

---

## How It Works

```
Detect → Backtest → Validate → Holdout → Live Re-run (every 3 days)
```

1. **Detect** — scan price/volume/patent data for candidate events (e.g. volume 2× the 60-day average)
2. **Backtest** — entry at T+1 open, hold N trading days, exit at open; deduct 10 bps slippage
3. **Validate** — paired t-test comparing stock return vs sector ETF; p < 0.05 required to be "validated"
4. **Holdout** — one-time test on reserved 2025+ data the system never trained on; results are final
5. **Live re-run** — every 3 days, fresh prices are pulled and signals re-checked; Top 10 only shows stocks with a signal fired in the last 90 days

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
| **Risk Level** | LOW / MED / HIGH based on how much individual trade returns vary |

---

## Automation

- **Ingest + signals:** GitHub Actions runs every 3 days, triggers Railway to pull fresh prices and re-run all signals
- **Rotation log:** after each ingest, a snapshot of the Top 10 is saved; changes (entered / exited / rank moved) are recorded
- **Failure alerts:** email sent to the configured address if the scheduled job fails

---

## How to Run Locally

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run python -m signalalpha.wiki.app   # → http://127.0.0.1:8000
uv run python -m signalalpha.ingest_prices
uv run python scripts/run_signal_patent_telecom.py
uv run python -m signalalpha.wiki.autogen
```

---

## Project Structure

```
src/signalalpha/
  signals/           # Signal detectors (volume_anomaly, patent_cluster …)
  wiki/
    app.py           # FastAPI web UI (dashboard + API endpoints)
    autogen.py       # Wiki page scaffolder + AUTOGEN section updater
    brief.py         # Daily brief builder
    validate.py      # Wiki page validator
  live_signals.py    # Runs all validated signals on current data
  ingest_prices.py   # Price ingestion
  ingest_patents.py  # Patent ingestion (PatentsView S3 bulk files)
scripts/             # One-off research scripts (backtests, sweeps, holdout)
wiki/                # Research pages (signals, companies, sectors)
.github/workflows/   # Scheduled ingest job (every 3 days) with failure email
```

---

## Disclaimer

SignalAlpha surfaces historical statistical patterns only. Past edge does not guarantee future results. All results are backtested and may not reflect live trading conditions. Nothing here constitutes investment advice.
