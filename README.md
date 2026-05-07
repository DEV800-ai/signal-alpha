# SignalAlpha

A systematic signal research and ranking system. Detects statistical edges in market data, validates them via backtesting, and presents results in a live dashboard with three investment modes.

> **This is not financial advice. No buy/sell recommendations are generated.**

---

## Dashboard

```bash
uv run python -m signalalpha.wiki.app
# Open http://127.0.0.1:8000
```

### Tabs

| Tab | Description |
|-----|-------------|
| **Daily Brief** | Validation status for every signal run — p-value, alpha, Sharpe, context freshness |
| **Top 10** | Ranked stock leaderboard with Long / Mid-term / Short modes |
| **Wiki Editor** | Browse and validate wiki pages; run the auto-generator |
| **How It Works** | Full explainer — metrics, pipeline, statistical methodology |

### Top 10 — Three Ranking Modes

**▲ Long** — stocks where the signal consistently precedes above-sector returns.
Ranked by: `alpha × hit_rate × log(N)`

**📈 Mid-term (1–3 months, lower risk)** — stocks with positive alpha and low volatility, suitable for patient holds of 1–3 months without large drawdown risk.
Ranked by: `(alpha / volatility) × hit_rate × log(N)` — an Information Ratio score that penalises high-variance names.

Each stock shows a **risk indicator** (LOW / MED / HIGH) based on return volatility:
- 🟢 LOW — std < 10% (stable compounders)
- 🟡 MED — std 10–20%
- 🔴 HIGH — std > 20% (high-volatility names)

**▼ Short** — stocks where the signal reliably fires before underperformance vs the sector ETF.
Ranked by: `|alpha| × (1 − hit_rate) × log(N)`

All modes support filters: signal quality (validated / borderline / all), sector (ai_infra / space_defense / telecom), and ranking method.

---

## Signal Pipeline

```
Detect → Backtest → Validate → Holdout
```

1. **Detect** — scan historical price / volume / SEC filing data for candidate events
2. **Backtest** — simulate entry at T+1 open, hold N trading days, exit at open; deduct 10 bps slippage
3. **Validate** — paired t-test comparing stock return vs sector ETF over the same window; p < 0.05 required
4. **Holdout** — one-time out-of-sample test on reserved 2025+ data; results are final and not used to re-tune

---

## Current Validated Signals

| Signal | Hold | N (in-sample) | Alpha | p-value | Holdout |
|--------|------|---------------|-------|---------|---------|
| Volume Anomaly ×2.0 — **15d hold** ★ | 15d | 1,480 | +1.27% | 0.0046 | +1.58%, Sharpe 1.22 |
| Volume Anomaly ×2.0 — 10d hold | 10d | 1,480 | +1.10% | 0.0061 | +1.24% |
| Volume Anomaly ×2.0 — 20d hold | 20d | 1,480 | +1.42% | 0.0062 | — |

**Volume Anomaly** fires when a ticker's 5-day average volume exceeds 2× its 60-day median. Debounced to one firing per 5 trading days. Entry at T+1 open.

Signals graveyard: 8-K excl. earnings (failed holdout p=0.27), earnings surprise Q75, sector-scoped volume anomaly variants.

---

## Universe

68 public companies across three sectors:

| Sector | Benchmark ETF | Examples |
|--------|--------------|---------|
| AI Infrastructure | SOXX | NVDA, AMD, MSFT, PLTR, SMCI |
| Space & Defense | ITA | LMT, NOC, RTX, KTOS, RKLB |
| Telecom | IYZ | TMUS, VERIZON, QCOM, LUMN |

---

## Key Metrics

| Metric | Definition |
|--------|-----------|
| **Alpha vs Sector** | stock return − sector ETF return over hold period |
| **Hit Rate** | % of signal firings that closed with a positive net return |
| **Avg Return** | mean net return after 10 bps round-trip slippage |
| **Volatility** | std deviation of net returns — used as risk proxy |
| **p-value** | paired t-test significance of alpha vs sector (< 0.05 = validated) |
| **Sharpe** | mean / std × √(252 / hold_days) — annualized risk-adjusted return |
| **Risk Level** | LOW (std < 10%) / MED (10–20%) / HIGH (> 20%) |

---

## How to Run

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies
uv sync

# Start the web UI
uv run python -m signalalpha.wiki.app
# → http://127.0.0.1:8000

# Ingest price data
uv run python -m signalalpha.ingest_prices

# Run a signal backtest
uv run python scripts/run_signal_vol_ai_infra.py

# Hold period sweep
uv run python scripts/run_hold_period_sweep.py

# Holdout validation (one-time)
uv run python scripts/run_holdout_validation.py

# Validate a wiki page
uv run python -m signalalpha.wiki.validate wiki/signals/volume_anomaly_5_60_t2.0__hold15d.md

# Refresh all AUTOGEN sections
uv run python -m signalalpha.wiki.autogen
```

---

## Project Structure

```
src/signalalpha/
  signals/           # Signal detectors (volume_anomaly, filing_8k, earnings_surprise …)
  wiki/
    app.py           # FastAPI web UI
    autogen.py       # Wiki page scaffolder + AUTOGEN section updater
    brief.py         # Daily brief builder (signal_runs → ranked summary)
    validate.py      # Wiki page validator (4 passes)
scripts/
  run_hold_period_sweep.py      # Hold period sweep runner
  run_holdout_validation.py     # Out-of-sample validation (one-time)
  backfill_events.py            # Backfill signal_events for existing runs
wiki/
  signals/           # Signal research pages (one per signal variant)
  companies/public/  # Company pages (68 tickers, auto-generated + hand-written)
data/
  signalalpha.duckdb # DuckDB database (not committed)
schemas/             # Wiki frontmatter schema definitions
```

---

## Disclaimer

SignalAlpha surfaces historical statistical patterns only. Past edge does not guarantee future results. All results are backtested — they may not reflect live trading conditions. Nothing here constitutes investment advice.
