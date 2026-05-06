"""8-K filing presence signal.

Definition (v1): an event is a (ticker, filing_date) pair where the company
filed any 8-K. Multiple 8-Ks on the same day are deduplicated to a single
event. To avoid overlap with the earnings signal, the `exclude_earnings`
variant drops 8-Ks whose item codes contain 2.02 (results-of-operations).

8-Ks have no intra-day timing in the EDGAR submissions index — assume EOD
filing convention; backtest enters T+1 open.
"""
from __future__ import annotations

import pandas as pd

from signalalpha.db import connect


def detect(exclude_earnings: bool = False) -> pd.DataFrame:
    """Return events DataFrame with columns: ticker, event_date, items_sample."""
    con = connect(read_only=True)
    try:
        df = con.execute(
            "SELECT ticker, filing_date AS event_date, items "
            "FROM sec_filings WHERE form = '8-K' "
            "ORDER BY ticker, filing_date"
        ).fetchdf()
    finally:
        con.close()

    if exclude_earnings:
        # Drop rows where the only or first item is 2.02. We keep filings that
        # combine 2.02 with material non-earnings items (rare, but possible).
        def is_earnings_only(items: str | None) -> bool:
            if not items:
                return False
            codes = [c.strip() for c in items.split(",")]
            non_admin = [c for c in codes if c != "9.01"]  # 9.01 = financial exhibits
            return non_admin == ["2.02"]
        mask = df["items"].apply(is_earnings_only)
        df = df[~mask]

    # Dedupe: one event per ticker per filing_date, keep the first items string.
    df = df.sort_values(["ticker", "event_date"])
    df = df.groupby(["ticker", "event_date"], as_index=False).agg(items_sample=("items", "first"))
    df["event_date"] = pd.to_datetime(df["event_date"])
    return df
