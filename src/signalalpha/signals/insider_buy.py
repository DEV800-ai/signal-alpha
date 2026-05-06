"""Insider open-market purchase signal (Form 4 transactionCode = 'P').

Definition: an event is a (ticker, filing_date) where one or more insiders
made open-market purchases above a threshold $ amount in aggregate. Filings
on the same day are summed before the threshold check.

Insider buying has historically shown a real edge — insiders rarely buy on
the open market unless they expect upside (vs. selling, which has many
non-signal reasons like diversification or option exercise).
"""
from __future__ import annotations

import pandas as pd

from signalalpha.db import connect


def detect(min_usd: float = 100_000.0) -> pd.DataFrame:
    """Aggregate P-coded transactions per (ticker, filing_date), return events
    where the total purchase amount meets the threshold."""
    con = connect(read_only=True)
    try:
        df = con.execute(
            "SELECT ticker, filing_date AS event_date, "
            "       sum(transaction_usd) AS total_usd, "
            "       count(*) AS n_tx, "
            "       count(DISTINCT insider_name) AS n_insiders "
            "FROM sec_form4 "
            "WHERE transaction_code = 'P' AND transaction_usd > 0 "
            "GROUP BY ticker, filing_date"
        ).fetchdf()
    finally:
        con.close()
    df = df[df["total_usd"] >= min_usd].copy()
    df["event_date"] = pd.to_datetime(df["event_date"])
    return df.sort_values("event_date").reset_index(drop=True)
