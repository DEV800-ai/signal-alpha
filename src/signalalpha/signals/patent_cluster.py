"""Patent-grant cluster signal detector.

Fires when a ticker receives ≥ N patent grants within any rolling 30-day window.
Debounced: one firing per ticker per 30 trading days to avoid re-firing on the
same cluster.

Event date = the date the Nth grant lands (the cluster completion date).
"""
from __future__ import annotations

import pandas as pd

from signalalpha.db import connect

DEFAULT_MIN_GRANTS = 5
DEFAULT_WINDOW_DAYS = 30
DEFAULT_DEBOUNCE_DAYS = 30


def detect(
    min_grants: int = DEFAULT_MIN_GRANTS,
    window_days: int = DEFAULT_WINDOW_DAYS,
    debounce_days: int = DEFAULT_DEBOUNCE_DAYS,
    sectors: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of (ticker, event_date, signal_name) for patent clusters.

    Args:
        min_grants:    minimum grants in the rolling window to fire.
        window_days:   rolling window in calendar days.
        debounce_days: suppress re-firing within this many days of a prior event.
        sectors:       restrict to specific sectors; None = all.
    """
    con = connect(read_only=True)

    sector_filter = ""
    params: list = []
    if sectors:
        placeholders = ", ".join("?" * len(sectors))
        sector_filter = f"AND u.sector IN ({placeholders})"
        params = list(sectors)

    # Pull all patent grants joined to universe (only tickers in our universe).
    grants_df = con.execute(f"""
        SELECT p.ticker, p.grant_date::DATE AS grant_date
        FROM patents p
        JOIN universe u ON u.ticker = p.ticker
        WHERE 1=1 {sector_filter}
        ORDER BY p.ticker, p.grant_date
    """, params).df()

    con.close()

    if grants_df.empty:
        return pd.DataFrame(columns=["ticker", "event_date", "signal_name"])

    grants_df["grant_date"] = pd.to_datetime(grants_df["grant_date"])
    signal_name = (
        f"patent_cluster_n{min_grants}_w{window_days}d"
    )

    events: list[dict] = []

    for ticker, grp in grants_df.groupby("ticker"):
        dates = grp["grant_date"].sort_values().reset_index(drop=True)
        last_fired: pd.Timestamp | None = None

        for i in range(len(dates)):
            current = dates.iloc[i]

            # Debounce: skip if we fired within debounce_days.
            if last_fired is not None:
                if (current - last_fired).days < debounce_days:
                    continue

            # Count grants in the rolling window ending at current date.
            window_start = current - pd.Timedelta(days=window_days - 1)
            count = ((dates >= window_start) & (dates <= current)).sum()

            if count >= min_grants:
                events.append({
                    "ticker":      ticker,
                    "event_date":  current.date(),
                    "signal_name": signal_name,
                })
                last_fired = current

    return pd.DataFrame(events, columns=["ticker", "event_date", "signal_name"])
