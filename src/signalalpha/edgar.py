"""SEC EDGAR client.

Polite by default: sets a User-Agent identifying the project + email and rate-
limits to <10 req/sec per SEC's fair-access policy. All endpoints are JSON.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import pandas as pd
import requests
from tqdm import tqdm

from signalalpha.config import EDGAR_USER_AGENT
from signalalpha.db import connect

_BASE_DATA = "https://data.sec.gov"
_BASE_WWW = "https://www.sec.gov"

_session = requests.Session()
_session.headers.update({
    "User-Agent": EDGAR_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
})
_lock = threading.Lock()
_last_request_at = [0.0]
_MIN_INTERVAL = 0.11  # ~9 req/sec, leaves headroom under SEC's 10/sec ceiling


def _get_json(url: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        with _lock:
            wait = _MIN_INTERVAL - (time.monotonic() - _last_request_at[0])
            if wait > 0:
                time.sleep(wait)
            _last_request_at[0] = time.monotonic()
        try:
            r = _session.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return None


def load_ticker_cik_map() -> dict[str, str]:
    """Map ticker -> 10-digit CIK string. SEC publishes a master file."""
    data = _get_json(f"{_BASE_WWW}/files/company_tickers.json")
    if not data:
        return {}
    out: dict[str, str] = {}
    for _, rec in data.items():
        ticker = rec["ticker"].upper()
        cik = f"{int(rec['cik_str']):010d}"
        out[ticker] = cik
    return out


@dataclass
class Filing:
    accession: str
    cik: str
    ticker: str
    form: str
    filing_date: str
    report_date: str | None
    primary_doc: str
    items: str | None


def _flatten_recent(payload: dict, ticker: str, cik: str) -> list[Filing]:
    recent = payload.get("filings", {}).get("recent", {})
    if not recent:
        return []
    n = len(recent.get("accessionNumber", []))
    out: list[Filing] = []
    for i in range(n):
        out.append(Filing(
            accession=recent["accessionNumber"][i],
            cik=cik,
            ticker=ticker,
            form=recent["form"][i],
            filing_date=recent["filingDate"][i],
            report_date=recent["reportDate"][i] or None,
            primary_doc=recent.get("primaryDocument", [""] * n)[i],
            items=recent.get("items", [None] * n)[i] or None,
        ))
    return out


def _flatten_older_file(payload: dict, ticker: str, cik: str) -> list[Filing]:
    n = len(payload.get("accessionNumber", []))
    out: list[Filing] = []
    for i in range(n):
        out.append(Filing(
            accession=payload["accessionNumber"][i],
            cik=cik,
            ticker=ticker,
            form=payload["form"][i],
            filing_date=payload["filingDate"][i],
            report_date=payload["reportDate"][i] or None,
            primary_doc=payload.get("primaryDocument", [""] * n)[i],
            items=payload.get("items", [None] * n)[i] or None,
        ))
    return out


def fetch_all_filings(ticker: str, cik: str) -> list[Filing]:
    payload = _get_json(f"{_BASE_DATA}/submissions/CIK{cik}.json")
    if not payload:
        return []
    out = _flatten_recent(payload, ticker, cik)
    for older_ref in payload.get("filings", {}).get("files", []):
        name = older_ref.get("name")
        if not name:
            continue
        older = _get_json(f"{_BASE_DATA}/submissions/{name}")
        if older:
            out.extend(_flatten_older_file(older, ticker, cik))
    return out


def ingest_filings(forms_filter: tuple[str, ...] | None = None,
                   since: str = "2018-01-01") -> tuple[int, list[str]]:
    """Pull all filings for our universe and persist to sec_filings table.
    Returns (rows_inserted, list_of_failed_tickers)."""
    con = connect()
    tickers = [
        r[0] for r in con.execute(
            "SELECT u.ticker FROM universe u "
            "WHERE u.sector != 'benchmark' "
            "  AND u.ticker IN (SELECT DISTINCT ticker FROM prices)"
        ).fetchall()
    ]
    cik_map = load_ticker_cik_map()
    inserted = 0
    failed: list[str] = []
    for t in tqdm(tickers, desc="EDGAR submissions"):
        cik = cik_map.get(t)
        if not cik:
            failed.append(t)
            continue
        try:
            filings = fetch_all_filings(t, cik)
        except Exception as e:
            print(f"  {t} ({cik}): {e}")
            failed.append(t)
            continue
        if not filings:
            continue
        df = pd.DataFrame([f.__dict__ for f in filings])
        df = df[df["filing_date"] >= since]
        if forms_filter:
            df = df[df["form"].isin(forms_filter)]
        if df.empty:
            continue
        df = df.drop_duplicates(subset=["accession"])
        con.register("ftmp", df)
        con.execute(
            "INSERT OR IGNORE INTO sec_filings "
            "(accession, cik, ticker, form, filing_date, report_date, primary_doc, items) "
            "SELECT accession, cik, ticker, form, filing_date, report_date, primary_doc, items "
            "FROM ftmp"
        )
        con.unregister("ftmp")
        inserted += len(df)
    con.close()
    return inserted, failed


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--forms", default="8-K,4", help="Comma-separated form types to keep")
    args = p.parse_args()
    forms = tuple(f.strip() for f in args.forms.split(",")) if args.forms else None
    n, failed = ingest_filings(forms_filter=forms)
    print(f"\nInserted {n:,} filings (forms={forms}).")
    if failed:
        print(f"Failed: {failed}")
