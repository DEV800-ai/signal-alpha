"""Opportunity Potential Layer — research upside / asymmetry evaluation.

Evaluates 6 checks to assess whether a signal candidate still has meaningful
research potential, or whether the move may already be fully priced in.

  valuation_room       — are current multiples extreme for this style bucket?
  growth_support       — do fundamentals support continued opportunity?
  technical_extension  — is the price too extended after a large move?
  market_cap_asymmetry — does company size allow meaningful asymmetric upside?
  sector_tailwind      — is the sector in an active positive theme?
  risk_penalty         — are there structural risks that reduce the opportunity?

No buy/sell/hold recommendations are generated.
All checks return pass / warn / fail / unknown — never a trading signal.
"""
from __future__ import annotations

import datetime as dt

import duckdb

# ── Weights ────────────────────────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {
    "valuation_room":       0.20,
    "growth_support":       0.20,
    "technical_extension":  0.25,
    "market_cap_asymmetry": 0.15,
    "sector_tailwind":      0.10,
    "risk_penalty":         0.10,
}

STATUS_SCORE: dict[str, float] = {
    "pass":    1.0,
    "warn":    0.5,
    "unknown": 0.5,
    "fail":    0.0,
}

_UNKNOWN_THRESHOLD = 4  # ≥ this many unknowns → overall status = "unknown"

# ── Price history minimums ──────────────────────────────────────────────────────
_MIN_N50  = 28
_MIN_N200 = 120

# ── Sector tailwind table ──────────────────────────────────────────────────────

_SECTOR_TAILWIND: dict[str, tuple[str, str]] = {
    "ai_infra":      ("pass",
        "AI infrastructure sector has active capex and compute-demand tailwinds."),
    "space_defense": ("pass",
        "Space and defense sector benefits from government spending and geopolitical tailwinds."),
    "telecom":       ("warn",
        "Telecom is cyclical and selective; tailwinds are mixed."),
    "quantum":       ("warn",
        "Quantum sector has high long-term potential but high near-term uncertainty."),
}

# ── Growth sectors (mirrors human_quality config) ──────────────────────────────

_GROWTH_SECTORS = {"ai_infra", "space_defense"}


# ── Check builder ──────────────────────────────────────────────────────────────

def _check(status: str, reason: str) -> dict:
    return {"status": status, "score": STATUS_SCORE[status], "reason": reason}


# ── Individual checks ──────────────────────────────────────────────────────────

def _valuation_room(pe: float | None, pb: float | None, sector: str | None) -> dict:
    is_growth = (sector or "") in _GROWTH_SECTORS

    if pe is not None and pe > 0:
        if is_growth:
            if pe <= 60:
                return _check("pass",
                    f"P/E {pe:.1f} — not extreme for a growth-style company; valuation room appears intact.")
            if pe <= 100:
                return _check("warn",
                    f"P/E {pe:.1f} — elevated for a growth-style company; some upside may already be priced in.")
            return _check("fail",
                f"P/E {pe:.1f} — highly stretched; near-term upside may largely be priced in.")
        else:
            if pe <= 20:
                return _check("pass",
                    f"P/E {pe:.1f} — reasonable; valuation room appears intact.")
            if pe <= 35:
                return _check("warn",
                    f"P/E {pe:.1f} — elevated; strong earnings growth would be required to justify further expansion.")
            return _check("fail",
                f"P/E {pe:.1f} — stretched; meaningful multiple expansion from here may be limited.")

    if pb is not None and pb > 0:
        if pb < 1.0:
            return _check("pass",
                f"P/B {pb:.2f} — trading below book value; fundamental valuation room appears intact.")
        if pb < 5.0:
            return _check("warn",
                f"P/B {pb:.2f} — above book value; P/E unavailable to confirm remaining upside room.")
        return _check("warn",
            f"P/B {pb:.2f} — elevated relative to book; P/E unavailable.")

    return _check("unknown", "Valuation data unavailable in current database.")


def _growth_support(
    eps_yoy: float | None,
    eps_q: float | None,
    rev_growth: float | None,
) -> dict:
    signals: list[tuple[str, float]] = []
    if eps_yoy is not None:
        signals.append(("EPS YoY", eps_yoy))
    elif eps_q is not None:
        signals.append(("EPS Qtrly", eps_q))
    if rev_growth is not None:
        signals.append(("Revenue", rev_growth))

    if not signals:
        return _check("unknown", "Revenue and EPS growth data unavailable in current database.")

    positives = [(k, v) for k, v in signals if v > 0.05]
    negatives = [(k, v) for k, v in signals if v < -0.05]

    if positives and not negatives:
        best_k, best_v = max(positives, key=lambda x: x[1])
        return _check("pass",
            f"{best_k} growth {best_v*100:+.1f}% — positive fundamentals support the opportunity.")
    if negatives and not positives:
        worst_k, worst_v = min(negatives, key=lambda x: x[1])
        return _check("fail",
            f"{worst_k} declining {worst_v*100:+.1f}% — growth support for this opportunity is weak.")
    if signals:
        vals = "; ".join(f"{k} {v*100:+.1f}%" for k, v in signals)
        return _check("warn", f"Mixed growth signals ({vals}) — opportunity support is not conclusive.")

    return _check("warn", "Growth signals near zero — opportunity support is modest.")


def _technical_extension(
    close: float | None,
    sma50: float | None,
    sma200: float | None,
    n50: int,
    n200: int,
    close_12m_ago: float | None,
) -> dict:
    if close is None:
        return _check("unknown", "Insufficient price history to assess technical extension.")

    reasons: list[str] = []
    worst = "pass"

    def _degrade(new_status: str) -> None:
        nonlocal worst
        rank = {"pass": 0, "warn": 1, "fail": 2}
        if rank.get(new_status, 0) > rank.get(worst, 0):
            worst = new_status

    # Distance from SMA50
    if sma50 is not None and sma50 > 0 and n50 >= _MIN_N50:
        pct50 = (close - sma50) / sma50 * 100
        if pct50 > 30:
            reasons.append(f"price is {pct50:.0f}% above SMA50 — strongly extended short-term")
            _degrade("fail")
        elif pct50 > 15:
            reasons.append(f"price is {pct50:.0f}% above SMA50 — moderately extended")
            _degrade("warn")
        else:
            reasons.append(f"within normal range of SMA50 ({pct50:+.0f}%)")

    # Distance from SMA200
    if sma200 is not None and sma200 > 0 and n200 >= _MIN_N200:
        pct200 = (close - sma200) / sma200 * 100
        if pct200 > 80:
            reasons.append(f"{pct200:.0f}% above SMA200 — very extended from long-term average")
            _degrade("fail")
        elif pct200 > 40:
            reasons.append(f"{pct200:.0f}% above SMA200 — extended from long-term average")
            _degrade("warn")

    # 12-month return
    if close_12m_ago is not None and close_12m_ago > 0:
        ret12 = (close - close_12m_ago) / close_12m_ago * 100
        if ret12 > 300:
            reasons.append(f"12-month return +{ret12:.0f}% — parabolic move may limit near-term asymmetry")
            _degrade("fail")
        elif ret12 > 150:
            reasons.append(f"12-month return +{ret12:.0f}% — large run; upside may be partly priced in")
            _degrade("warn")
        elif ret12 > 0:
            reasons.append(f"12-month return +{ret12:.0f}%")

    if not reasons:
        return _check("unknown", "Insufficient price history to assess technical extension.")

    return _check(worst, "; ".join(reasons) + ".")


def _market_cap_asymmetry(market_cap: float | None) -> dict:
    if market_cap is None:
        return _check("unknown", "Market cap unavailable in current database.")

    B = 1e9
    if market_cap > 200 * B:
        cap_str = f"${market_cap/B:.0f}B"
        return _check("warn",
            f"Mega-cap ({cap_str}) — strong company, but asymmetric upside potential may be more limited.")
    if market_cap > 10 * B:
        cap_str = f"${market_cap/B:.0f}B"
        return _check("warn",
            f"Large-cap ({cap_str}) — reasonable size; moderate asymmetric upside potential.")
    if market_cap > 2 * B:
        cap_str = f"${market_cap/B:.1f}B"
        return _check("pass",
            f"Mid-cap ({cap_str}) — size allows meaningful asymmetric research upside.")
    if market_cap > 300e6:
        cap_str = f"${market_cap/1e6:.0f}M"
        return _check("pass",
            f"Small-cap ({cap_str}) — higher asymmetric upside potential if the signal holds.")
    cap_str = f"${market_cap/1e6:.0f}M"
    return _check("warn",
        f"Micro-cap ({cap_str}) — high upside potential but liquidity and execution risk apply.")


def _sector_tailwind(sector: str | None) -> dict:
    if not sector:
        return _check("unknown", "No sector data available for tailwind assessment.")
    entry = _SECTOR_TAILWIND.get(sector)
    if entry:
        return _check(entry[0], entry[1])
    return _check("unknown",
        f"Sector '{sector}' not in tailwind mapping — assess macro context manually.")


def _risk_penalty(human_quality: dict | None) -> dict:
    if not human_quality:
        return _check("unknown", "Human quality data unavailable for risk assessment.")

    checks = human_quality.get("checks", {})
    risks: list[str] = []

    if checks.get("liquidity", {}).get("status") == "fail":
        risks.append("low liquidity")
    if checks.get("trend", {}).get("status") == "fail":
        risks.append("price below 200d MA")
    if checks.get("market_alignment", {}).get("status") == "fail":
        risks.append("broad market below 200d MA")
    if checks.get("eps_growth", {}).get("status") == "fail":
        risks.append("EPS declining significantly")

    if not risks:
        return _check("pass", "No major structural penalties detected from available data.")
    if len(risks) == 1:
        return _check("warn", f"One notable risk factor: {risks[0]}.")
    return _check("fail",
        f"Multiple structural risk factors: {', '.join(risks)}.")


def _summary(checks: dict[str, dict], status: str) -> str:
    LABELS = {
        "valuation_room":       "valuation",
        "growth_support":       "growth support",
        "technical_extension":  "technical extension",
        "market_cap_asymmetry": "market cap",
        "sector_tailwind":      "sector tailwind",
        "risk_penalty":         "risk",
    }
    grouped: dict[str, list[str]] = {"pass": [], "warn": [], "fail": [], "unknown": []}
    for k, c in checks.items():
        grouped[c["status"]].append(LABELS.get(k, k))

    parts: list[str] = []
    if grouped["pass"]:
        parts.append(f"Positive on {', '.join(grouped['pass'])}.")
    if grouped["warn"]:
        parts.append(f"Caution on {', '.join(grouped['warn'])}.")
    if grouped["fail"]:
        parts.append(f"Concern: {', '.join(grouped['fail'])}.")
    if grouped["unknown"]:
        parts.append(f"{', '.join(g.capitalize() for g in grouped['unknown'])} data unavailable.")

    prefix = {
        "high":    "Opportunity potential is high. ",
        "medium":  "Opportunity potential is medium. ",
        "low":     "Opportunity potential is low. ",
        "unknown": "Opportunity potential is uncertain — too much data is missing. ",
    }.get(status, "")
    return prefix + (" ".join(parts) or "No opportunity data available.")


# ── Batch public API ───────────────────────────────────────────────────────────

def evaluate_opportunity_batch(
    db: duckdb.DuckDBPyConnection,
    tickers: list[str],
    sector_map: dict[str, str],
    as_of_date: str | None = None,
    human_quality_map: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Evaluate opportunity potential for multiple tickers in two DB round-trips."""
    if not tickers:
        return {}

    today  = as_of_date or str(dt.date.today())
    hq_map = human_quality_map or {}

    # ── Round-trip 1: price data ───────────────────────────────────────────────
    ph = ", ".join("?" for _ in tickers)
    price_rows = db.execute(f"""
        SELECT
            ticker,
            LAST(close ORDER BY date)                                                          AS cur,
            AVG(close)   FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '50 days')          AS sma50,
            COUNT(close) FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '50 days')          AS n50,
            AVG(close)   FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '200 days')         AS sma200,
            COUNT(close) FILTER (WHERE date >= CAST(? AS DATE) - INTERVAL '200 days')         AS n200,
            FIRST(close ORDER BY date) FILTER (
                WHERE date BETWEEN CAST(? AS DATE) - INTERVAL '395 days'
                              AND CAST(? AS DATE) - INTERVAL '335 days'
            )                                                                                  AS c12m
        FROM prices
        WHERE ticker IN ({ph}) AND date <= CAST(? AS DATE)
        GROUP BY ticker
    """, [today, today, today, today, today, today, *tickers, today]).fetchall()

    price_data: dict[str, tuple] = {r[0]: r[1:] for r in price_rows}

    # ── Round-trip 2: fundamentals ─────────────────────────────────────────────
    fund_data: dict[str, tuple] = {}
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    if "fundamentals" in tables:
        try:
            fund_rows = db.execute(f"""
                SELECT DISTINCT ON (ticker)
                    ticker, trailing_pe, forward_pe, price_to_book,
                    eps_growth_yoy, eps_growth_quarterly,
                    market_cap, revenue_growth
                FROM fundamentals
                WHERE ticker IN ({ph})
                ORDER BY ticker, as_of_date DESC
            """, tickers).fetchall()
            fund_data = {r[0]: r[1:] for r in fund_rows}
        except Exception:
            # Columns may not exist on first deploy before schema migration runs
            pass

    # ── Build results ──────────────────────────────────────────────────────────
    results: dict[str, dict] = {}
    for tkr in tickers:
        sector = sector_map.get(tkr, "")
        hq     = hq_map.get(tkr)

        pd = price_data.get(tkr)
        cur = sma50 = sma200 = c12m = None
        n50 = n200 = 0
        if pd:
            cur, sma50, n50, sma200, n200, c12m = pd
            n50  = int(n50  or 0)
            n200 = int(n200 or 0)

        fd = fund_data.get(tkr)
        trailing_pe = forward_pe = pb = eps_yoy = eps_q = market_cap = rev_growth = None
        if fd:
            trailing_pe, forward_pe, pb, eps_yoy, eps_q, market_cap, rev_growth = fd
        pe = trailing_pe if (trailing_pe is not None and trailing_pe > 0) else forward_pe

        checks = {
            "valuation_room":       _valuation_room(pe, pb, sector),
            "growth_support":       _growth_support(eps_yoy, eps_q, rev_growth),
            "technical_extension":  _technical_extension(cur, sma50, sma200, n50, n200, c12m),
            "market_cap_asymmetry": _market_cap_asymmetry(market_cap),
            "sector_tailwind":      _sector_tailwind(sector),
            "risk_penalty":         _risk_penalty(hq),
        }

        n_unknown = sum(1 for c in checks.values() if c["status"] == "unknown")
        score = round(sum(checks[k]["score"] * w for k, w in WEIGHTS.items()), 4)

        if n_unknown >= _UNKNOWN_THRESHOLD:
            status = "unknown"
        elif score >= 0.75:
            status = "high"
        elif score >= 0.45:
            status = "medium"
        else:
            status = "low"

        results[tkr] = {
            "ticker":     tkr,
            "as_of_date": today,
            "checks":     checks,
            "score":      score,
            "status":     status,
            "summary":    _summary(checks, status),
        }

    return results


def evaluate_opportunity_potential(
    db: duckdb.DuckDBPyConnection,
    ticker: str,
    sector: str | None = None,
    as_of_date: str | None = None,
    human_quality: dict | None = None,
) -> dict:
    """Evaluate opportunity potential for a single ticker."""
    return evaluate_opportunity_batch(
        db, [ticker], {ticker: sector or ""},
        as_of_date=as_of_date,
        human_quality_map={ticker: human_quality} if human_quality else {},
    ).get(ticker, _empty_result(ticker, as_of_date))


def _empty_result(ticker: str, as_of_date: str | None) -> dict:
    unknown = _check("unknown", "No data available.")
    checks = {k: unknown for k in WEIGHTS}
    return {
        "ticker":     ticker,
        "as_of_date": as_of_date or str(dt.date.today()),
        "checks":     checks,
        "score":      0.5,
        "status":     "unknown",
        "summary":    "Opportunity potential is uncertain — insufficient data available.",
    }
