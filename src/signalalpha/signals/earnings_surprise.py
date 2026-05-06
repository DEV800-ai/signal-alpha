"""Earnings-surprise signal.

Definition: a firing event is an earnings announcement whose % surprise is in
the TOP QUARTILE of all announcements in the iteration window. The event_date
returned uses the BMO/AMC-adjusted date so the backtest enters at the correct
next trading day's open.

Quartile threshold is computed on the iteration window only (not 2025) so the
holdout is not used for calibration. The threshold is exposed so downstream
runs can use the same cutoff on the holdout.
"""
from __future__ import annotations

import pandas as pd

from signalalpha.config import ITERATION_END
from signalalpha.db import connect


def detect(
    quantile: float = 0.75,
    cutoff_date: str = ITERATION_END,
) -> tuple[pd.DataFrame, float]:
    """Return (events DataFrame, surprise_pct threshold used)."""
    con = connect(read_only=True)
    try:
        df = con.execute(
            "SELECT ticker, event_date_adj AS event_date, surprise_pct "
            "FROM earnings_events WHERE surprise_pct IS NOT NULL"
        ).fetchdf()
    finally:
        con.close()
    df = df.dropna(subset=["surprise_pct"])
    df["event_date"] = pd.to_datetime(df["event_date"])
    iter_window = df[df["event_date"] <= pd.Timestamp(cutoff_date)]
    threshold = float(iter_window["surprise_pct"].quantile(quantile))
    fires = df[df["surprise_pct"] >= threshold].copy()
    return fires, threshold
