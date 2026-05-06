# SignalAlpha

A signal-driven research system. Detects statistical edges in market data, validates them via backtest, and organizes the research in a structured wiki.

**This is not financial advice. No buy/sell recommendations are generated.**

---

## What it does

```
Signal fires → backtest validates edge → wiki documents context → user understands in <30 seconds
```

Signals currently tracked: volume anomaly, earnings surprise, SEC 8-K filings, insider buying.

---

## How to run

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies
uv sync

# Start the web UI
uv run python -m signalalpha.wiki.app
# Open http://127.0.0.1:8000
```

**Ingest data:**
```bash
uv run python -m signalalpha.ingest_prices
uv run python -m signalalpha.ingest_earnings
```

**Run validator CLI:**
```bash
uv run python -m signalalpha.wiki.validate wiki/signals/volume_anomaly_5_60_t2.0.md
```

**Run tests:**
```bash
uv run pytest tests/
```

---

## Project structure

```
src/signalalpha/
  signals/        # Signal detection logic
  wiki/           # Validator, auto-generator, web UI
wiki/signals/     # Signal research pages (markdown)
schemas/          # Wiki schema definitions
data/             # DuckDB database (not committed)
```

---

## Disclaimer

SignalAlpha surfaces historical statistical patterns only. Past edge does not guarantee future results. Nothing here constitutes investment advice.
