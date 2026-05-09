"""Human Quality Layer — context filters for Top Research Candidates.

Evaluates 5 filters:
  liquidity        — 30d average daily volume (from prices table)
  trend            — price vs 50d / 200d moving averages (from prices table)
  eps_growth       — year-over-year EPS growth (from fundamentals table)
  valuation        — P/E and P/B ratios (from fundamentals table)
  market_alignment — sector ETF + SPY vs their 200d MAs (from prices table)

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

# 200 calendar days ≈ 136 trading days (weekends + ~7 US holidays).
# 50 calendar days ≈ 34 trading days.
# Set thresholds slightly below to handle gaps without false unknowns.
_MIN_ROWS_200D = 120
_MIN_ROWS_50D  = 28

# P/E thresholds by sector style
_GROWTH_SECTORS = {"ai_infra", "space_defense"}
_PE_PASS_GROWTH = 60
_PE_WARN_GROWTH = 100
_PE_PASS_VALUE  = 20
_PE_WARN_VALUE  = 35


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


def _eps_growth(growth_yoy: float | None, growth_q: float | None) -> dict:
    # Use YoY as primary, quarterly as secondary signal
    g = growth_yoy if growth_yoy is not None else growth_q
    if g is None:
        return _check("unknown", "EPS growth data unavailable.")
    pct = f"{g*100:+.1f}%"
    src = "YoY" if growth_yoy is not None else "quarterly"
    if g > 0.10:
        return _check("pass", f"EPS growing {pct} ({src}) — positive earnings momentum.")
    if g >= 0:
        return _check("warn", f"EPS growth {pct} ({src}) — modest, watch for acceleration.")
    if g >= -0.10:
        return _check("warn", f"EPS declining {pct} ({src}) — mild deterioration.")
    return _check("fail", f"EPS declining {pct} ({src}) — significant earnings pressure.")


def _valuation(pe: float | None, pb: float | None, sector: str | None) -> dict:
    is_growth = (sector or "") in _GROWTH_SECTORS
    pe_pass   = _PE_PASS_GROWTH if is_growth else _PE_PASS_VALUE
    pe_warn   = _PE_WARN_GROWTH if is_growth else _PE_WARN_VALUE
    style     = "growth" if is_growth else "value"

    if pe is not None and pe > 0:
        if pe <= pe_pass:
            return _check("pass",
                f"P/E {pe:.1f} — reasonable for a {style}-style company.")
        if pe <= pe_warn:
            return _check("warn",
                f"P/E {pe:.1f} — elevated for a {style}-style company.")
        return _check("warn",
            f"P/E {pe:.1f} — stretched valuation for a {style}-style company.")

    if pb is not None and pb > 0:
        if pb < 1.0:
            return _check("pass", f"P/B {pb:.2f} — trading below book value.")
        return _check("warn", f"P/B {pb:.2f} — above book value; P/E unavailable.")

    return _check("unknown", "P/E and P/B data unavailable.")


def _market_alignment(etf_above: bool | None, spy_above: bool | None) -> dict:
    knowns = [x for x in (etf_above, spy_above) if x is not None]
    if not knowns:
        return _check("unknown",
            "Benchmark price data not yet ingested — will resolve on next data refresh.")
    n_pass = sum(knowns)
    if n_pass == len(knowns):
        return _check("pass", "Sector benchmark and SPY are both above their 200d MA.")
    if n_pass == 0:
        return _check("fail", "Sector benchmark and SPY are both below their 200d MA.")
    return _check("warn", "Mixed market: one benchmark above 200d MA, the other below.")


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
        parts.append(
            f"{', '.join(g.capitalize() for g in grouped['unknown'])} data unavailable.")
    return " ".join(parts) or "No quality data available."


# ── Fundamentals helper ────────────────────────────────────────────────────────

def _load_fundamentals(
    db: duckdb.DuckDBPyConnection,
    tickers: list[str],
) -> dict[str, tuple]:
    """Return {ticker: (trailing_pe, forward_pe, pb, trailing_eps, eps_yoy, eps_q)}."""
    if not tickers:
        return {}
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    if "fundamentals" not in tables:
        return {}
    ph = ", ".join("?" for _ in tickers)
    rows = db.execute(f"""
        SELECT DISTINCT ON (ticker)
            ticker, trailing_pe, forward_pe, price_to_book,
            trailing_eps, eps_growth_yoy, eps_growth_quarterly
        FROM fundamentals
        WHERE ticker IN ({ph})
        ORDER BY ticker, as_of_date DESC
    """, tickers).fetchall()
    return {r[0]: r[1:] for r in rows}


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_human_quality(
    db: duckdb.DuckDBPyConnection,
    ticker: str,
    sector: str | None = None,
    as_of_date: str | None = None,
) -> dict:
    """Evaluate human quality filters for a single ticker."""
    return evaluate_human_quality_batch(
        db, [ticker], {ticker: sector or ""}, as_of_date
    ).get(ticker, _empty_result(ticker, as_of_date))


def evaluate_human_quality_batch(
    db: duckdb.DuckDBPyConnection,
    tickers: list[str],
    sector_map: dict[str, str],
    as_of_date: str | None = None,
) -> dict[str, dict]:
    """Evaluate human quality filters for multiple tickers in two DB round-trips."""
    if not tickers:
        return {}

    today = as_of_date or str(dt.date.today())

    sector_etfs = {SECTOR_BENCHMARKS[s] for s in sector_map.values() if s in SECTOR_BENCHMARKS}
    benchmarks  = sector_etfs | {BROAD_BENCHMARK}
    all_tkrs    = list(set(tickers) | benchmarks)

    # ── Round-trip 1: price data (liquidity, trend, market alignment) ──────────
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

    price_data: dict[str, tuple] = {r[0]: r[1:] for r in rows}

    # ── Round-trip 2: fundamentals (EPS growth, valuation) ────────────────────
    fund_data = _load_fundamentals(db, tickers)

    def _above_200(tkr: str) -> bool | None:
        if tkr not in price_data:
            return None
        _, cl, _, _, sm200, n200 = price_data[tkr]
        if cl is None or sm200 is None or (n200 or 0) < _MIN_ROWS_200D:
            return None
        return bool(cl > sm200)

    results: dict[str, dict] = {}
    for tkr in tickers:
        sector     = sector_map.get(tkr, "")
        sector_etf = SECTOR_BENCHMARKS.get(sector)

        d = price_data.get(tkr)
        avg_vol = latest_close = sma50 = sma200 = None
        n50 = n200 = 0
        if d:
            avg_vol, latest_close, sma50, n50, sma200, n200 = d
            n50  = int(n50  or 0)
            n200 = int(n200 or 0)

        f = fund_data.get(tkr)
        trailing_pe = forward_pe = pb = trailing_eps = eps_yoy = eps_q = None
        if f:
            trailing_pe, forward_pe, pb, trailing_eps, eps_yoy, eps_q = f

        # Use trailing PE first, fall back to forward PE
        pe = trailing_pe if trailing_pe is not None and trailing_pe > 0 else forward_pe

        checks = {
            "liquidity":        _liquidity(avg_vol),
            "trend":            _trend(latest_close, sma50, sma200, n50, n200),
            "eps_growth":       _eps_growth(eps_yoy, eps_q),
            "valuation":        _valuation(pe, pb, sector),
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
