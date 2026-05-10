"""Ranking logic for the Top 10 endpoint.

No FastAPI imports — all functions accept/return plain Python types so they
can be called directly in tests without spinning up the web server.
"""
from __future__ import annotations

import duckdb

VALID_FILTERS   = {"all", "validated", "borderline"}
VALID_SECTORS   = {"all", "ai_infra", "space_defense", "telecom"}
VALID_SCORE     = {"composite", "alpha", "hitrate", "blended"}
VALID_DIRECTION = {"long", "short", "midterm", "opportunity"}

NUMERIC_COLS = (
    "avg_alpha", "avg_return", "std_return", "hit_rate",
    "composite_score", "short_score", "abs_alpha", "short_hit_rate",
    "midterm_score", "opp_score", "pct_vs_50d",
)


def resolve_direction(direction: str, score_by: str) -> tuple[str, str, str]:
    """Return (dir_having, order_col, order_dir) for the given direction."""
    if direction == "long":
        dir_having = ""
        _sb = "composite" if score_by == "blended" else score_by
        order_col = {"composite": "composite_score", "alpha": "avg_alpha", "hitrate": "hit_rate"}[_sb]
    elif direction == "short":
        dir_having = "AND AVG(se.alpha_sector) < 0"
        _sb = "composite" if score_by == "blended" else score_by
        order_col = {"composite": "short_score", "alpha": "abs_alpha", "hitrate": "short_hit_rate"}[_sb]
    elif direction == "opportunity":
        dir_having = "AND AVG(se.alpha_sector) > 0 AND STDDEV(se.net_return) > 0"
        order_col = "opp_score"
    else:  # midterm
        dir_having = "AND AVG(se.alpha_sector) > 0 AND STDDEV(se.net_return) > 0"
        order_col = "midterm_score"
    return dir_having, order_col, "DESC"


def fetch_rankings(
    db: duckdb.DuckDBPyConnection,
    *,
    signal_filter: str = "validated",
    sector: str = "all",
    direction: str = "long",
    score_by: str = "composite",
    recency_days: int = 90,
    limit: int = 10,
) -> tuple[list[dict], str]:
    """Run the ranking query and return (stocks, order_col).

    Inputs are assumed to be already validated against the VALID_* sets.
    """
    sig_cond = (
        "AND sr.p_value_vs_sector < 0.05"      if signal_filter == "validated"
        else "AND sr.p_value_vs_sector < 0.10" if signal_filter == "borderline"
        else ""
    )
    sec_cond = f"AND u.sector = '{sector}'" if sector != "all" else ""
    recency_having = (
        f"AND MAX(se.event_date) >= CURRENT_DATE - INTERVAL '{recency_days} days'"
        if recency_days > 0 else ""
    )
    dir_having, order_col, order_dir = resolve_direction(direction, score_by)

    rows = db.execute(f"""
        WITH sma50_cte AS (
            SELECT ticker,
                   LAST(close ORDER BY date) AS current_price,
                   AVG(close) FILTER (WHERE date >= CURRENT_DATE - INTERVAL '50 days') AS sma50
            FROM prices
            GROUP BY ticker
        )
        SELECT se.ticker, u.name, u.sector,
               COUNT(*)                                                                    AS n_signals,
               AVG(se.alpha_sector)                                                        AS avg_alpha,
               AVG(se.net_return)                                                          AS avg_return,
               STDDEV(se.net_return)                                                       AS std_return,
               SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                 / NULLIF(COUNT(*), 0)                                                     AS hit_rate,
               MAX(se.event_date)                                                          AS last_signal,
               -- Long composite: alpha × hit_rate × log(n+1)
               AVG(se.alpha_sector)
                 * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                    / NULLIF(COUNT(*), 0))
                 * LN(COUNT(*) + 1)                                                        AS composite_score,
               -- Short composite: |alpha| × (1 − hit_rate) × log(n+1)
               ABS(AVG(se.alpha_sector))
                 * (1 - SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                          / NULLIF(COUNT(*), 0))
                 * LN(COUNT(*) + 1)                                                        AS short_score,
               ABS(AVG(se.alpha_sector))                                                   AS abs_alpha,
               1 - SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                     / NULLIF(COUNT(*), 0)                                                 AS short_hit_rate,
               -- Mid-term score: (alpha / std) × hit_rate × log(n+1)
               CASE WHEN STDDEV(se.net_return) > 0
                    THEN (AVG(se.alpha_sector) / STDDEV(se.net_return))
                           * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                              / NULLIF(COUNT(*), 0))
                           * LN(COUNT(*) + 1)
                    ELSE 0 END                                                             AS midterm_score,
               -- Opportunity: composite × (1 + dip_bonus) — rewards stocks below 50d MA
               CASE WHEN sma.sma50 IS NOT NULL AND sma.current_price < sma.sma50
                    THEN (AVG(se.alpha_sector)
                           * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                              / NULLIF(COUNT(*), 0))
                           * LN(COUNT(*) + 1))
                         * (1 + GREATEST(0, (sma.sma50 - sma.current_price)
                                          / NULLIF(sma.sma50, 0)) * 3)
                    ELSE (AVG(se.alpha_sector)
                           * (SUM(CASE WHEN se.net_return > 0 THEN 1.0 ELSE 0.0 END)
                              / NULLIF(COUNT(*), 0))
                           * LN(COUNT(*) + 1))
                    END                                                                    AS opp_score,
               -- % vs 50d MA (negative = below = dip)
               CASE WHEN sma.sma50 IS NOT NULL AND sma.sma50 > 0
                    THEN ROUND((sma.current_price / sma.sma50 - 1) * 100, 1)
                    ELSE NULL END                                                          AS pct_vs_50d
        FROM signal_events se
        JOIN signal_runs sr ON sr.run_id = se.run_id
        JOIN universe    u  ON u.ticker  = se.ticker
        LEFT JOIN sma50_cte sma ON sma.ticker = se.ticker
        -- Only use the latest run per signal_name to avoid double-counting
        JOIN (
            SELECT signal_name, MAX(run_id) AS latest_run_id
            FROM signal_runs
            GROUP BY signal_name
        ) lr ON lr.signal_name = sr.signal_name AND lr.latest_run_id = sr.run_id
        WHERE 1=1 {sig_cond} {sec_cond}
        GROUP BY se.ticker, u.name, u.sector, sma.current_price, sma.sma50
        HAVING COUNT(*) >= 5 {dir_having} {recency_having}
        ORDER BY {order_col} {order_dir} NULLS LAST
        LIMIT ?
    """, [limit]).fetchall()

    cols = [
        "ticker", "name", "sector", "n_signals",
        "avg_alpha", "avg_return", "std_return", "hit_rate", "last_signal",
        "composite_score", "short_score", "abs_alpha", "short_hit_rate",
        "midterm_score", "opp_score", "pct_vs_50d",
    ]
    stocks = []
    for r in rows:
        d = dict(zip(cols, r))
        d["last_signal"] = str(d["last_signal"])[:10] if d["last_signal"] else None
        for k in NUMERIC_COLS:
            d[k] = round(float(d[k]), 6) if d[k] is not None else None
        stocks.append(d)

    return stocks, order_col
