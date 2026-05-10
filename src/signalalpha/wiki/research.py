"""Backend logic for GET /api/research/{ticker}.

Builds a deterministic research pack from existing DB tables and wiki files.
No LLM calls. No buy/sell/hold recommendations.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb

from signalalpha.quality.human_quality import evaluate_human_quality_batch
from signalalpha.opportunity.opportunity_potential import evaluate_opportunity_batch
from signalalpha.portfolio.portfolio_context import build_portfolio_context

_FORBIDDEN = ("buy", "sell", "hold", "recommend", "target price", "stop loss")

_CHECK_LABELS = {
    "liquidity": "liquidity", "trend": "price trend",
    "market_alignment": "market alignment", "eps_growth": "EPS growth",
    "valuation": "valuation",
}
_OPP_LABELS = {
    "valuation_room": "valuation", "growth_support": "growth",
    "technical_extension": "technical extension", "market_cap_asymmetry": "market cap",
    "sector_tailwind": "sector tailwind", "risk_penalty": "risk flags",
}


def _signal_stats(db: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    """Best-signal stats for a ticker — picks the run with the lowest p-value."""
    row = db.execute("""
        SELECT sr.signal_name,
               COUNT(*)                                                          AS n_events,
               AVG(se.alpha_sector)                                              AS alpha,
               SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                 / NULLIF(COUNT(*), 0)                                           AS hit_rate,
               MIN(sr.p_value_vs_sector)                                         AS p_value
        FROM signal_events se
        JOIN signal_runs sr ON sr.run_id = se.run_id
        JOIN (SELECT signal_name, MAX(run_id) AS latest_run_id
              FROM signal_runs GROUP BY signal_name) lr
          ON lr.signal_name = sr.signal_name AND lr.latest_run_id = sr.run_id
        WHERE se.ticker = ?
        GROUP BY sr.signal_name
        ORDER BY MIN(sr.p_value_vs_sector) ASC NULLS LAST
        LIMIT 1
    """, [ticker]).fetchone()

    if not row:
        return None

    name, n_events, alpha, hit_rate, p_value = row
    if p_value is not None and p_value < 0.05:
        status = "validated"
    elif p_value is not None and p_value < 0.10:
        status = "borderline"
    else:
        status = "exploratory"

    alpha_f   = float(alpha)   if alpha    is not None else None
    hit_rate_f = float(hit_rate) if hit_rate is not None else None
    p_value_f = float(p_value) if p_value  is not None else None
    n = int(n_events) if n_events else 0

    parts = [f"This signal has fired {n} times historically"]
    if alpha_f is not None:
        parts.append(f"averaging {alpha_f*100:+.1f}% alpha vs its sector benchmark")
    if hit_rate_f is not None:
        parts.append(f"with a {round(hit_rate_f*100)}% win rate")
    summary = ", ".join(parts) + ". " + (
        "It is statistically validated (p < 0.05)."              if status == "validated"
        else "It shows borderline statistical significance (p < 0.10)."  if status == "borderline"
        else "Statistical significance is limited — use with extra caution."
    )

    return {
        "name":     name,
        "alpha":    round(alpha_f, 4)    if alpha_f    is not None else None,
        "p_value":  round(p_value_f, 4) if p_value_f  is not None else None,
        "n_events": n,
        "hit_rate": round(hit_rate_f, 4) if hit_rate_f is not None else None,
        "status":   status,
        "summary":  summary,
    }


def _wiki_context(ticker: str, wiki_root: Path) -> dict:
    """Wiki page existence, age, and freshness for a ticker."""
    rel_path  = f"wiki/companies/public/{ticker}.md"
    page_path = wiki_root / "companies" / "public" / f"{ticker}.md"

    if not page_path.exists():
        return {
            "company_page":    rel_path,
            "has_company_page": False,
            "freshness_status": "missing",
            "last_updated":     None,
            "last_reviewed":    None,
        }

    mtime     = dt.datetime.fromtimestamp(page_path.stat().st_mtime).date()
    days_old  = (dt.date.today() - mtime).days
    freshness = "current" if days_old <= 30 else "stale"

    # Parse `last_reviewed` from YAML frontmatter if present
    last_reviewed = None
    try:
        for line in page_path.read_text(encoding="utf-8").splitlines()[:25]:
            if line.strip().startswith("last_reviewed:"):
                last_reviewed = line.split(":", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass

    return {
        "company_page":    rel_path,
        "has_company_page": True,
        "freshness_status": freshness,
        "last_updated":     str(mtime),
        "last_reviewed":    last_reviewed,
    }


def _recent_appearances(db: duckdb.DuckDBPyConnection, ticker: str) -> list[dict]:
    """Recent appearances in top10_snapshots, newest first."""
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    if "top10_snapshots" not in tables:
        return []
    rows = db.execute("""
        SELECT snapshot_date, direction, rank
        FROM top10_snapshots
        WHERE ticker = ?
        ORDER BY snapshot_date DESC
        LIMIT 10
    """, [ticker]).fetchall()
    return [{"date": str(r[0])[:10], "direction": r[1], "rank": r[2]} for r in rows]


def _next_steps(context: dict, hq: dict) -> list[str]:
    """Deterministic investigation checklist derived from current data state."""
    checks = hq.get("checks", {})
    steps: list[str] = []

    if context["has_company_page"]:
        steps.append("Review the company wiki page for recent developments and context.")
    else:
        steps.append("No company wiki page yet — run Autogen to generate one.")

    if context["freshness_status"] == "stale":
        steps.append("Company context is stale (>30 days) — verify before relying on this candidate.")

    steps.append("Verify what caused the signal to fire recently — check price action around the event date.")
    steps.append("Check recent SEC filings and catalysts (earnings, partnerships, officer changes).")

    trend_status = checks.get("trend", {}).get("status")
    if trend_status in ("warn", "fail"):
        steps.append("Price trend is mixed or declining — check moving average alignment before proceeding.")

    mkt_status = checks.get("market_alignment", {}).get("status")
    if mkt_status == "fail":
        steps.append("Broad market is below its 200d MA — consider macro context.")

    if checks.get("eps_growth", {}).get("status") == "unknown":
        steps.append("EPS growth data unavailable — verify earnings trajectory manually.")

    if checks.get("valuation", {}).get("status") == "unknown":
        steps.append("Valuation data unavailable — check P/E or P/B ratio manually.")

    return steps


def _why_here(signal: dict | None, hq: dict, opp: dict) -> dict:
    """Four-point explanation of why this ticker appears as a research candidate."""
    # 1. Signal line
    if signal is None:
        signal_line = "No signal data found for this ticker."
        signal_level = "none"
    else:
        status = signal["status"]
        alpha_pct = f"{signal['alpha']*100:+.1f}%" if signal.get("alpha") is not None else "—"
        n = signal.get("n_events", 0)
        p = signal.get("p_value")
        p_str = f"p={p:.3f}" if p is not None else ""
        if status == "validated":
            signal_line = (
                f"Statistically validated signal ({p_str}) — {alpha_pct} avg alpha "
                f"vs sector across {n} historical events."
            )
        elif status == "borderline":
            signal_line = (
                f"Borderline signal ({p_str}) — shows edge but below the p<0.05 threshold. "
                f"{alpha_pct} avg alpha across {n} events."
            )
        else:
            signal_line = (
                f"Exploratory signal — limited statistical significance. "
                f"{alpha_pct} avg alpha across {n} events."
            )
        signal_level = status

    # 2. Quality line
    checks = hq.get("checks", {})
    fails = [k for k, v in checks.items() if v.get("status") == "fail"]
    warns = [k for k, v in checks.items() if v.get("status") == "warn"]
    if not checks:
        quality_line = "Quality data unavailable."
    elif not fails and not warns:
        quality_line = "Passes all quality checks — liquidity, trend, market alignment, and fundamentals look healthy."
    elif fails:
        labels = [_CHECK_LABELS.get(f, f) for f in fails]
        quality_line = f"Quality concern{'s' if len(fails) > 1 else ''} flagged on: {', '.join(labels)}."
        if warns:
            quality_line += f" Caution on: {', '.join(_CHECK_LABELS.get(w, w) for w in warns)}."
    else:
        quality_line = f"Mostly passes quality checks. Caution on: {', '.join(_CHECK_LABELS.get(w, w) for w in warns)}."

    # 3. Opportunity line
    opp_status = opp.get("status", "unknown")
    opp_checks = opp.get("checks", {})
    opp_fails = [k for k, v in opp_checks.items() if v.get("status") == "fail"]
    if opp_status == "high":
        opp_line = "Research upside looks strong — most opportunity checks pass."
    elif opp_status == "medium":
        if opp_fails:
            labels = [_OPP_LABELS.get(f, f) for f in opp_fails]
            opp_line = f"Research upside is medium. Concern on: {', '.join(labels)}."
        else:
            opp_line = "Research upside is medium — some caution flags but no hard blocks."
    elif opp_status == "low":
        if opp_fails:
            labels = [_OPP_LABELS.get(f, f) for f in opp_fails]
            opp_line = f"Research upside looks limited. Key concerns: {', '.join(labels)}."
        else:
            opp_line = "Research upside looks limited across multiple opportunity checks."
    else:
        opp_line = "Opportunity potential is unknown — insufficient data to assess research upside."

    # 4. Main caution — single most important concern, pulling from reason text when available
    caution: str | None = None
    for f in fails:
        reason = checks[f].get("reason", "")
        if reason:
            caution = reason
            break
    if not caution:
        for f in opp_fails:
            reason = opp_checks[f].get("reason", "")
            if reason:
                caution = reason
                break
    if not caution and signal and signal.get("status") != "validated":
        caution = "Signal is not fully statistically validated — use with extra caution."
    if not caution:
        for w in warns:
            reason = checks[w].get("reason", "")
            if reason:
                caution = reason
                break
    if not caution:
        caution = "No major concerns identified from available data."

    return {
        "signal":       signal_line,
        "signal_level": signal_level,
        "quality":      quality_line,
        "opportunity":  opp_line,
        "main_caution": caution,
    }


def build_research(
    db: duckdb.DuckDBPyConnection,
    ticker: str,
    wiki_root: Path,
) -> dict:
    """Assemble the full research pack for a single ticker. Always returns a valid dict."""
    ticker = ticker.upper()

    sector_row = db.execute(
        "SELECT sector FROM universe WHERE ticker = ?", [ticker]
    ).fetchone()
    sector = sector_row[0] if sector_row else None

    signal  = _signal_stats(db, ticker)
    quality = evaluate_human_quality_batch(db, [ticker], {ticker: sector or ""})
    hq      = quality.get(ticker, {})
    opp_map = evaluate_opportunity_batch(
        db, [ticker], {ticker: sector or ""},
        human_quality_map={ticker: hq},
    )
    opp     = opp_map.get(ticker, {})
    context = _wiki_context(ticker, wiki_root)
    history = _recent_appearances(db, ticker)
    steps   = _next_steps(context, hq)
    why     = _why_here(signal, hq, opp)
    portfolio = build_portfolio_context(
        ticker=ticker,
        sector=sector or "",
        signal_data=signal,
        human_quality=hq,
        opportunity=opp,
    )

    return {
        "ticker":         ticker,
        "candidate_type": "Top Research Candidate",
        "why_here":       why,
        "portfolio_context": portfolio,
        "signal":         signal,
        "human_quality":  {
            "score":   hq.get("score"),
            "checks":  hq.get("checks", {}),
            "summary": hq.get("summary", ""),
        },
        "opportunity_potential": {
            "score":   opp.get("score"),
            "status":  opp.get("status"),
            "checks":  opp.get("checks", {}),
            "summary": opp.get("summary", ""),
        },
        "context":    context,
        "history":    {"recent_appearances": history},
        "next_steps": steps,
    }
