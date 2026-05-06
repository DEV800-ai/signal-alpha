"""Pull historical earnings announcements + EPS surprises into DuckDB.

Source: yfinance `get_earnings_dates`. Stores BMO/AMC session classification
and a session-adjusted event_date so downstream signals can use a clean
"act on next trading day's open" convention with no look-ahead.
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from signalalpha.config import PRICE_HISTORY_START
from signalalpha.db import connect


def _session_and_adj(ts: pd.Timestamp) -> tuple[str, pd.Timestamp]:
    """Classify announcement as BMO (<12h) or AMC (>=12h) and adjust event_date
    so backtest's 'next trading day strictly after event_date' lands on the
    correct entry day. BMO -> shift back 1 day so entry is same-day open."""
    if ts.hour < 12:
        return "bmo", (ts.normalize() - pd.Timedelta(days=1))
    return "amc", ts.normalize()


def pull_for_ticker(ticker: str) -> list[dict]:
    df = yf.Ticker(ticker).get_earnings_dates(limit=80)
    if df is None or df.empty:
        return []
    df = df.reset_index()
    rows: list[dict] = []
    for _, r in df.iterrows():
        est, act = r.get("EPS Estimate"), r.get("Reported EPS")
        if pd.isna(est) or pd.isna(act):
            continue
        ts = pd.to_datetime(r["Earnings Date"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None) if ts.tz_localize else ts.tz_convert(None)
        # Skip announcements past today's date (forecasts) or before our data starts
        if ts >= pd.Timestamp.today():
            continue
        if ts < pd.Timestamp(PRICE_HISTORY_START):
            continue
        session, adj = _session_and_adj(ts)
        # Surprise % with guard against tiny denominators
        if abs(float(est)) < 0.05:
            surprise_pct = float("nan")
        else:
            surprise_pct = (float(act) - float(est)) / abs(float(est)) * 100.0
        rows.append({
            "ticker": ticker,
            "event_date": ts,
            "event_date_adj": adj.date(),
            "session": session,
            "eps_estimate": float(est),
            "eps_actual": float(act),
            "surprise_pct": surprise_pct,
        })
    return rows


def ingest_all(sleep_between: float = 0.05) -> int:
    con = connect()
    tickers = [
        r[0] for r in con.execute(
            "SELECT u.ticker FROM universe u "
            "WHERE u.sector != 'benchmark' "
            "  AND u.ticker IN (SELECT DISTINCT ticker FROM prices)"
        ).fetchall()
    ]
    con.execute("DELETE FROM earnings_events")
    total = 0
    for t in tqdm(tickers, desc="Earnings"):
        try:
            rows = pull_for_ticker(t)
        except Exception as e:
            print(f"  {t}: {e}")
            continue
        if not rows:
            continue
        df = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "event_date"])
        con.register("ev_df", df)
        con.execute("INSERT INTO earnings_events SELECT * FROM ev_df")
        con.unregister("ev_df")
        total += len(df)
        if sleep_between:
            time.sleep(sleep_between)
    con.close()
    return total


if __name__ == "__main__":
    n = ingest_all()
    print(f"\nIngested {n:,} earnings events.")
