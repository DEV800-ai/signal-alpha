"""Fetch patent grants from USPTO PatentsView API into the patents table.

API: https://search.patentsview.org/api/v1/patent/
Free, no authentication required.
Rate limit: ~45 requests/minute — we sleep 1.5s between requests.

Incremental: skips tickers where the latest grant_date in DB >= yesterday.
Idempotent: patent_id is the PRIMARY KEY, so re-runs are safe.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import pandas as pd
import requests

from signalalpha.config import DATA_DIR
from signalalpha.db import connect

PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"
ASSIGNEES_CSV = DATA_DIR / "patent_assignees.csv"
HISTORY_START = "2018-01-01"
_SLEEP = 1.5  # seconds between requests


@dataclass
class PatentIngestStats:
    ticker: str
    rows_inserted: int = 0
    last_date: dt.date | None = None
    error: str | None = None


def _last_grant_date(con, ticker: str) -> dt.date | None:
    row = con.execute(
        "SELECT MAX(grant_date) FROM patents WHERE ticker = ?", [ticker]
    ).fetchone()
    return row[0] if row and row[0] else None


def _fetch_page(assignee_query: str, start: str, end: str, page: int) -> dict:
    params = {
        "q": (
            f'{{"_and":[{{"_gte":{{"patent_date":"{start}"}}}},'
            f'{{"_lte":{{"patent_date":"{end}"}}}},'
            f'{{"_contains":{{"assignee_organization":"{assignee_query}"}}}}]}}'
        ),
        "f": '["patent_id","patent_date","assignee_organization"]',
        "o": f'{{"per_page":1000,"page":{page}}}',
    }
    resp = requests.get(PATENTSVIEW_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def ingest_ticker(con, ticker: str, assignee_query: str) -> PatentIngestStats:
    stats = PatentIngestStats(ticker=ticker)
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)

    last = _last_grant_date(con, ticker)
    if last and last >= yesterday:
        return stats  # already current

    start = str((last + dt.timedelta(days=1))) if last else HISTORY_START
    end = str(today)

    rows: list[dict] = []
    page = 1
    while True:
        try:
            data = _fetch_page(assignee_query, start, end, page)
        except Exception as e:
            stats.error = str(e)
            return stats

        patents = data.get("patents") or []
        for p in patents:
            patent_id = p.get("patent_id")
            grant_date = p.get("patent_date")
            assignee = p.get("assignee_organization", "")
            if patent_id and grant_date:
                rows.append({
                    "patent_id":     patent_id,
                    "grant_date":    grant_date,
                    "ticker":        ticker,
                    "assignee_name": assignee,
                })

        total = data.get("total_patent_count", 0)
        if page * 1000 >= total:
            break
        page += 1
        time.sleep(_SLEEP)

    if not rows:
        return stats

    df = pd.DataFrame(rows)
    df["grant_date"] = pd.to_datetime(df["grant_date"]).dt.date

    # Upsert — ignore conflicts on patent_id PRIMARY KEY.
    con.execute("""
        INSERT OR IGNORE INTO patents (patent_id, grant_date, ticker, assignee_name)
        SELECT patent_id, grant_date::DATE, ticker, assignee_name
        FROM df
    """)

    stats.rows_inserted = len(df)
    stats.last_date = df["grant_date"].max()
    return stats


def ingest_all() -> list[PatentIngestStats]:
    if not ASSIGNEES_CSV.exists():
        raise FileNotFoundError(f"Patent assignees mapping not found: {ASSIGNEES_CSV}")

    assignees = pd.read_csv(ASSIGNEES_CSV)
    con = connect(read_only=False)
    results = []

    for _, row in assignees.iterrows():
        ticker = row["ticker"]
        query = row["assignee_query"]
        print(f"  {ticker}: fetching '{query}' …", end=" ", flush=True)
        stats = ingest_ticker(con, ticker, query)
        if stats.error:
            print(f"ERROR — {stats.error}")
        elif stats.rows_inserted:
            print(f"{stats.rows_inserted} rows → {stats.last_date}")
        else:
            print("up to date")
        results.append(stats)
        time.sleep(_SLEEP)

    con.close()
    return results


if __name__ == "__main__":
    print("Ingesting patent grants from PatentsView …")
    results = ingest_all()
    total = sum(r.rows_inserted for r in results)
    errors = [r for r in results if r.error]
    print(f"\nDone. {total} rows inserted. {len(errors)} errors.")
