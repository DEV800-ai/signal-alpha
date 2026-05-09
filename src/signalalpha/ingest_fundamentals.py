"""Fetch EPS growth and valuation data via yfinance and store in DuckDB.

Fields fetched per ticker (from yfinance ticker.info):
  trailing_pe          — trailing 12-month P/E ratio
  forward_pe           — forward P/E ratio
  price_to_book        — P/B ratio
  trailing_eps         — trailing 12-month EPS (USD)
  eps_growth_yoy       — year-over-year earnings growth (decimal, e.g. 0.12 = +12%)
  eps_growth_quarterly — most recent quarter EPS growth vs prior year

One row per ticker per run date. Existing rows for the same date are replaced.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import yfinance as yf
from tqdm import tqdm

from signalalpha.db import connect

SOURCE = "yfinance_fundamentals"

_FIELDS = (
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "trailingEps",
    "earningsGrowth",
    "earningsQuarterlyGrowth",
)


@dataclass
class FundamentalsStats:
    ticker: str
    fetched: bool
    error: str | None = None


def _safe_float(info: dict, key: str) -> float | None:
    val = info.get(key)
    try:
        f = float(val)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _eps_growth_from_income_stmt(tkr_obj: yf.Ticker) -> float | None:
    """Compute YoY EPS growth from annual income statement (Diluted EPS row).

    Used as a fallback when earningsGrowth is not available in ticker.info.
    Handles negative prior-year EPS correctly via abs(prior).
    """
    try:
        stmt = tkr_obj.income_stmt
        if stmt is None or stmt.empty:
            return None
        eps_rows = [r for r in stmt.index if "Diluted EPS" in str(r)]
        if not eps_rows:
            return None
        eps = stmt.loc[eps_rows[0]].dropna().sort_index(ascending=False)
        if len(eps) < 2:
            return None
        current, prior = float(eps.iloc[0]), float(eps.iloc[1])
        if prior == 0:
            return None
        return (current - prior) / abs(prior)
    except Exception:
        return None


def ingest_ticker(con, ticker: str, as_of_date: dt.date) -> FundamentalsStats:
    try:
        tkr_obj = yf.Ticker(ticker)
        info    = tkr_obj.info
    except Exception as e:
        return FundamentalsStats(ticker=ticker, fetched=False, error=str(e))

    if not info or info.get("quoteType") is None:
        return FundamentalsStats(ticker=ticker, fetched=False, error="empty info")

    trailing_pe          = _safe_float(info, "trailingPE")
    forward_pe           = _safe_float(info, "forwardPE")
    price_to_book        = _safe_float(info, "priceToBook")
    trailing_eps         = _safe_float(info, "trailingEps")
    eps_growth_yoy       = _safe_float(info, "earningsGrowth")
    eps_growth_quarterly = _safe_float(info, "earningsQuarterlyGrowth")

    # Fall back to income statement computation when yfinance doesn't carry earningsGrowth
    if eps_growth_yoy is None and eps_growth_quarterly is None:
        eps_growth_yoy = _eps_growth_from_income_stmt(tkr_obj)

    con.execute("""
        INSERT INTO fundamentals
            (ticker, as_of_date, trailing_pe, forward_pe, price_to_book,
             trailing_eps, eps_growth_yoy, eps_growth_quarterly, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT (ticker, as_of_date) DO UPDATE SET
            trailing_pe          = excluded.trailing_pe,
            forward_pe           = excluded.forward_pe,
            price_to_book        = excluded.price_to_book,
            trailing_eps         = excluded.trailing_eps,
            eps_growth_yoy       = excluded.eps_growth_yoy,
            eps_growth_quarterly = excluded.eps_growth_quarterly,
            fetched_at           = excluded.fetched_at
    """, [ticker, as_of_date, trailing_pe, forward_pe, price_to_book,
          trailing_eps, eps_growth_yoy, eps_growth_quarterly])

    return FundamentalsStats(ticker=ticker, fetched=True)


def ingest_all(sleep_between: float = 0.3) -> list[FundamentalsStats]:
    con = connect()
    today = dt.date.today()
    tickers = [r[0] for r in con.execute(
        "SELECT ticker FROM universe WHERE sector != 'benchmark' ORDER BY ticker"
    ).fetchall()]

    stats: list[FundamentalsStats] = []
    for t in tqdm(tickers, desc="Ingesting fundamentals"):
        stats.append(ingest_ticker(con, t, today))
        if sleep_between:
            time.sleep(sleep_between)

    con.close()

    fetched = sum(1 for s in stats if s.fetched)
    failed  = [s for s in stats if s.error]
    print(f"\nFundamentals: {fetched}/{len(stats)} tickers fetched.")
    if failed:
        print(f"{len(failed)} failed:")
        for s in failed:
            print(f"  {s.ticker}: {s.error}")

    return stats


if __name__ == "__main__":
    ingest_all()
