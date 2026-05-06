"""Pull daily OHLCV from yfinance into DuckDB. Incremental + idempotent."""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from signalalpha.config import PRICE_HISTORY_START, UNIVERSE_CSV
from signalalpha.db import connect

SOURCE = "yfinance"


@dataclass
class IngestStats:
    ticker: str
    rows_inserted: int
    last_date: dt.date | None
    error: str | None = None


def _load_universe_into_db(con) -> None:
    df = pd.read_csv(UNIVERSE_CSV, parse_dates=["active_from", "active_to"])
    df["active_from"] = df["active_from"].dt.date
    df["active_to"] = df["active_to"].dt.date
    con.execute("DELETE FROM universe")
    con.register("uni_df", df)
    con.execute("INSERT INTO universe SELECT * FROM uni_df")
    con.unregister("uni_df")


def _last_ingested_date(con, ticker: str) -> dt.date | None:
    row = con.execute(
        "SELECT date FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        [ticker],
    ).fetchone()
    return row[0] if row and row[0] else None


def _fetch_one(ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end + dt.timedelta(days=1)).isoformat(),  # yf end is exclusive
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index().rename(columns=str.lower)
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"]).dt.date
    keep = ["ticker", "date", "open", "high", "low", "close", "volume"]
    return df[keep]


def ingest_ticker(con, ticker: str, force_full: bool = False) -> IngestStats:
    today = dt.date.today()
    if force_full:
        start = dt.date.fromisoformat(PRICE_HISTORY_START)
    else:
        last = _last_ingested_date(con, ticker)
        start = (last + dt.timedelta(days=1)) if last else dt.date.fromisoformat(PRICE_HISTORY_START)
    if start > today:
        return IngestStats(ticker=ticker, rows_inserted=0, last_date=start - dt.timedelta(days=1))
    try:
        df = _fetch_one(ticker, start, today)
    except Exception as e:  # network / API errors
        return IngestStats(ticker=ticker, rows_inserted=0, last_date=None, error=str(e))
    if df.empty:
        return IngestStats(ticker=ticker, rows_inserted=0, last_date=None)
    con.register("price_df", df)
    con.execute("INSERT OR IGNORE INTO prices SELECT * FROM price_df")
    con.unregister("price_df")
    new_last = df["date"].max()
    con.execute(
        """
        INSERT INTO ingestion_log (source, ticker, last_date, fetched_at, rows_inserted)
        VALUES (?, ?, ?, now(), ?)
        ON CONFLICT (source, ticker) DO UPDATE SET
            last_date = excluded.last_date,
            fetched_at = excluded.fetched_at,
            rows_inserted = ingestion_log.rows_inserted + excluded.rows_inserted
        """,
        [SOURCE, ticker, new_last, len(df)],
    )
    return IngestStats(ticker=ticker, rows_inserted=len(df), last_date=new_last)


def ingest_all(force_full: bool = False, sleep_between: float = 0.0) -> list[IngestStats]:
    con = connect()
    _load_universe_into_db(con)
    tickers = [r[0] for r in con.execute("SELECT ticker FROM universe ORDER BY ticker").fetchall()]
    stats: list[IngestStats] = []
    for t in tqdm(tickers, desc="Ingesting prices"):
        stats.append(ingest_ticker(con, t, force_full=force_full))
        if sleep_between:
            time.sleep(sleep_between)
    con.close()
    return stats


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true", help="Re-pull from PRICE_HISTORY_START")
    args = p.parse_args()
    results = ingest_all(force_full=args.full)
    inserted = sum(s.rows_inserted for s in results)
    failed = [s for s in results if s.error]
    print(f"\nInserted {inserted:,} rows across {len(results)} tickers.")
    if failed:
        print(f"\n{len(failed)} ticker(s) failed:")
        for s in failed:
            print(f"  {s.ticker}: {s.error}")
