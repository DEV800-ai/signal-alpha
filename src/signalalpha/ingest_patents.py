"""Fetch granted patents from the USPTO Open Data Portal into the patents table.

API: https://api.uspto.gov/api/v1/patent/applications/search
Free, no authentication required.
Rate limit: conservative 1.5s between requests.

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

USPTO_URL = "https://api.uspto.gov/api/v1/patent/applications/search"
ASSIGNEES_CSV = DATA_DIR / "patent_assignees.csv"
HISTORY_START = "2018-01-01"
_SLEEP = 1.5       # seconds between requests
_PAGE_SIZE = 25    # API default; max varies — keep conservative


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


def _fetch_page(assignee_query: str, start: str, end: str, offset: int) -> dict:
    body = {
        "q": f'applicationMetaData.firstApplicantName:"{assignee_query}"',
        "filters": [
            {
                "name": "applicationMetaData.applicationStatusDescriptionText",
                "value": ["Patented Case"],
            }
        ],
        "rangeFilters": [
            {
                "field": "applicationMetaData.grantDate",
                "valueFrom": start,
                "valueTo": end,
            }
        ],
        "fields": [
            "applicationNumberText",
            "applicationMetaData.grantDate",
            "applicationMetaData.firstApplicantName",
        ],
        "pagination": {
            "offset": offset,
            "limit": _PAGE_SIZE,
        },
    }
    resp = requests.post(USPTO_URL, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _extract_records(data: dict, ticker: str) -> list[dict]:
    """Parse the API response into a flat list of row dicts."""
    # Try known response envelope keys; fall back to scanning for a list value.
    for key in ("patentFileWrapperDataBag", "results", "applications", "patents"):
        bag = data.get(key)
        if isinstance(bag, list):
            break
    else:
        # Last resort: find the first list value in the response
        bag = next((v for v in data.values() if isinstance(v, list)), [])

    rows = []
    for record in bag:
        patent_id = record.get("applicationNumberText")
        meta = record.get("applicationMetaData") or {}
        grant_date = meta.get("grantDate")
        assignee = meta.get("firstApplicantName", "")
        if patent_id and grant_date:
            rows.append({
                "patent_id":     patent_id,
                "grant_date":    grant_date,
                "ticker":        ticker,
                "assignee_name": assignee,
            })
    return rows


def _total_count(data: dict) -> int:
    """Return total number of matching records from the API response."""
    for key in ("count", "totalCount", "total", "total_patent_count", "totalResults"):
        val = data.get(key)
        if isinstance(val, int):
            return val
    # Some responses bury the count in a metadata object
    meta = data.get("metaData") or data.get("metadata") or {}
    for key in ("count", "totalCount", "total"):
        val = meta.get(key)
        if isinstance(val, int):
            return val
    return 0


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
    offset = 0
    total = None

    while True:
        try:
            data = _fetch_page(assignee_query, start, end, offset)
        except Exception as e:
            stats.error = str(e)
            return stats

        page_rows = _extract_records(data, ticker)
        rows.extend(page_rows)

        if total is None:
            total = _total_count(data)

        offset += _PAGE_SIZE
        if not page_rows or offset >= (total or offset):
            break
        time.sleep(_SLEEP)

    if not rows:
        return stats

    df = pd.DataFrame(rows)
    df["grant_date"] = pd.to_datetime(df["grant_date"]).dt.date

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
    print("Ingesting granted patents from USPTO Open Data Portal …")
    results = ingest_all()
    total = sum(r.rows_inserted for r in results)
    errors = [r for r in results if r.error]
    print(f"\nDone. {total} rows inserted. {len(errors)} errors.")
