"""Volume anomaly signal.

Definition (from STRATEGY.md):
    5-day average volume > N x 60-day median, debounced to avoid clustering.

Signal observation is post-close on day T (we know T's volume); backtest
enters at T+1 open. No look-ahead: at signal-fire time, all inputs are
available (rolling windows are right-aligned, ending at T inclusive).

The strategy doc also requires "no 8-K or earnings within 3 days" — that
filter is applied downstream by the runner once the 8-K event table exists.
"""
from __future__ import annotations

import pandas as pd

from signalalpha.db import connect


def detect(
    threshold: float = 2.0,
    window_short: int = 5,
    window_long: int = 60,
    debounce_days: int = 5,
    sectors: tuple[str, ...] = ("ai_infra", "space_defense", "telecom"),
) -> pd.DataFrame:
    """Return events DataFrame with columns: ticker, event_date, ratio."""
    con = connect(read_only=True)
    try:
        prices = con.execute(
            f"""
            SELECT p.ticker, p.date, p.volume
            FROM prices p JOIN universe u USING (ticker)
            WHERE u.sector IN ({','.join(['?'] * len(sectors))})
            ORDER BY p.ticker, p.date
            """,
            list(sectors),
        ).fetchdf()
    finally:
        con.close()

    out_rows = []
    for ticker, g in prices.groupby("ticker", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < window_long + window_short:
            continue
        short_avg = g["volume"].rolling(window_short).mean()
        long_med = g["volume"].rolling(window_long).median()
        ratio = short_avg / long_med
        # Fire where ratio crosses threshold
        fires = ratio > threshold
        last_fire_idx = -10**9
        for i in range(len(g)):
            if not bool(fires.iloc[i]):
                continue
            if i - last_fire_idx <= debounce_days:
                continue
            out_rows.append({
                "ticker": ticker,
                "event_date": g["date"].iloc[i],
                "ratio": float(ratio.iloc[i]),
            })
            last_fire_idx = i

    return pd.DataFrame(out_rows)
