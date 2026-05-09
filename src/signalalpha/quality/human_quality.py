"""Human Quality Layer — context filters for Top Research Candidates.

Evaluates 5 filters using only data already in the database:
  liquidity        — 30d average daily volume
  trend            — price vs 50d / 200d moving averages
  eps_growth       — always unknown (no EPS data in DB)
  valuation        — always unknown (no P/E data in DB)
  market_alignment — sector ETF + SPY vs their 200d MAs

No trading recommendations are generated.
All filters return pass / warn / fail / unknown — never a buy/sell signal.
"""
from __future__ import annotations

import datetime as dt

import duckdb

from signalalpha.config import BROAD_BENCHMARK, SECTOR_BENCHMARKS

# ── Scoring weights ────────────────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {
    "liquidity":        0.25,
    "trend":            0.30,
    "eps_growth":       0.15,
    "valuation":        0.10,
    "market_alignment": 0.20,
}

STATUS_SCORE: dict[str, float] = {
    "pass":    1.0,
    "warn":    0.5,
    "unknown": 0.5,
    "fail":    0.0,
}

# Need at least this many trading-day rows within the window to trust the MA
_MIN_ROWS_200D = 140
_MIN_ROWS_50D  = 35


# ── Check builders ─────────────────────────────────────────────────────────────

def _check(status: str, reason: str) -> dict:
    return {"status": status, "score": STATUS_SCORE[status], "reason": reason}


def _liquidity(avg_vol: float | None) -> dict:
    if avg_vol is None:
        return _check("unknown", "No volume data available.")
    if avg_vol >= 500_000:
        return _check("pass",
            f"30d avg volume: {avg_vol/1_000_000:.1f}M shares — sufficient liquidity.")
    if avg_vol >= 250_000:
        return _check("warn",
            f"30d avg volume: {avg_vol/1_000:.0f}K shares — low, may affect execution.")
    return _check("fail",
        f"30d avg volume: {avg_vol/1_000:.0f}K shares — very low liquidity.")


def _trend(close: float | None, sma50: float | None, sma200: float | None,
           n50: int, n200: int) -> dict:
    if close is None or sma200 is None or n200 < _MIN_ROWS_200D:
        return _check("unknown", "Fewer than 200 trading days of price history.")
    if close > sma200:
        if sma50 is not None and n50 >= _MIN_ROWS_50D and sma50 > sma200:
            return _check("pass",
                f"Uptrend: close above 200d MA ({sma200:.2f}) and 50d MA above 200d MA.")
        return _check("warn",
            f"Mixed: close above 200d MA ({sma200:.2f}) but 50d MA is not confirming.")
    return _check("fail",
        f"Downtrend: close ({close:.2f}) is below 200d MA ({sma200:.2f}).")


def _market_alignment(etf_above: bool | None, spy_above: bool | None) -> dict:
    knowns = [x for x in (etf_above, spy_above) if x is not None]
    if not knowns:
        return _check("unknown", "Benchmark price data unavailable.")
    n_pass = sum(knowns)
    if n_pass == len(knowns):
        return _check("pass",
            "Sector benchmark and SPY are both above their 200d MA.")
    if n_pass == 0:
        return _check("fail",
            "Sector benchmark and SPY are both below their 200d MA.")
    return _check("warn",
        "Mixed market: one benchmark above 200d MA, the other below.")


def _summary(checks: dict[str, dict]) -> str:
    labels = {
        "liquidity": "liquidity", "trend": "trend",
        "eps_growth": "EPS growth", "valuation": "valuation",
        "market_alignment": "market alignment",
    }
    grouped: dict[str, list[str]] = {"pass": [], "warn": [], "fail": [], "unknown": []}
    for k, c in checks.items():
        grouped[c["status"]].append(labels[k])
    parts = []
    if grouped["pass"]:
        parts.append(f"Passes {', '.join(grouped['pass'])}.")
    if grouped["warn"]:
        parts.append(f"Caution on {', '.join(grouped['warn'])}.")
    if grouped["fail"]:
        parts.append(f"Fails {', '.join(grouped['fail'])}.")
    if grouped["unknown"]:
        parts.append(f"{', '.join(g.capitalize() for g in grouped['unknown'])} data unavailable.")
    return " ".join(parts) or "No quality data available."


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_human_quality(
    db: duckdb.DuckDBPyConnection,
    ticker: str,
    sector: str | None = None,
    as_of_date: str | None = None,
) -> dict:
    """Evaluate human quality filters for a single ticker.

    Returns a dict with keys: ticker, as_of_date, checks, score, summary.
    Never raises — returns unknown on any data gap.
    """
    return evaluate_human_quality_batch(
        db, [ticker], {ticker: sector or ""}, as_of_date
    ).get(ticker, _empty_result(ticker, as_of_date))


def evaluate_human_quality_batch(
    db: duckdb.DuckDBPyConnection,
    tickers: list[str],
    sector_map: dict[str, str],
    as_of_date: str | None = None,
) -> dict[str, dict]:
    """Evaluate human quality filters for multiple tickers in one DB round-trip."""
    if not tickers:
        return {}

    today = as_of_date or str(dt.date.today())

    sector_etfs = {SECTOR_BENCHMARKS[s] for s in sector_map.values() if s in SECTOR_BENCHMARKS}
    benchmarks  = sector_etfs | {BROAD_BENCHMARK}
    all_tkrs    = list(set(tickers) | benchmarks)

    ph = ", ".join("?" for _ in all_tkrs)
    rows = db.execute(f"""
        SELECT
            ticker,
            AVG(volume)  FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '30 days')  AS avg_vol,
            LAST(close ORDER BY date)                                                  AS latest_close,
            AVG(close)   FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '50 days')  AS sma50,
            COUNT(close) FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '50 days')  AS n50,
            AVG(close)   FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '200 days') AS sma200,
            COUNT(close) FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '200 days') AS n200
        FROM prices
        WHERE ticker IN ({ph}) AND date <= CAST(? AS DATE)
        GROUP BY ticker
    """, [today, today, today, today, today, *all_tkrs, today]).fetchall()

    data: dict[str, tuple] = {r[0]: r[1:] for r in rows}

    def _above_200(tkr: str) -> bool | None:
        if tkr not in data:
            return None
        _, cl, _, _, sm200, n200 = data[tkr]
        if cl is None or sm200 is None or (n200 or 0) < _MIN_ROWS_200D:
            return None
        return bool(cl > sm200)

    results: dict[str, dict] = {}
    for tkr in tickers:
        sector     = sector_map.get(tkr, "")
        sector_etf = SECTOR_BENCHMARKS.get(sector)

        d = data.get(tkr)
        avg_vol = latest_close = sma50 = sma200 = None
        n50 = n200 = 0
        if d:
            avg_vol, latest_close, sma50, n50, sma200, n200 = d
            n50  = int(n50  or 0)
            n200 = int(n200 or 0)

        checks = {
            "liquidity":        _liquidity(avg_vol),
            "trend":            _trend(latest_close, sma50, sma200, n50, n200),
            "eps_growth":       _check("unknown", "EPS data unavailable in current database."),
            "valuation":        _check("unknown", "P/E and P/B data unavailable in current database."),
            "market_alignment": _market_alignment(
                _above_200(sector_etf) if sector_etf else None,
                _above_200(BROAD_BENCHMARK),
            ),
        }
        score = round(sum(checks[k]["score"] * w for k, w in WEIGHTS.items()), 4)

        results[tkr] = {
            "ticker":     tkr,
            "as_of_date": today,
            "checks":     checks,
            "score":      score,
            "summary":    _summary(checks),
        }

    return results


def _empty_result(ticker: str, as_of_date: str | None) -> dict:
    unknown = _check("unknown", "No data available.")
    checks = {k: unknown for k in WEIGHTS}
    return {
        "ticker":     ticker,
        "as_of_date": as_of_date or str(dt.date.today()),
        "checks":     checks,
        "score":      0.5,
        "summary":    "No quality data available.",
    }
