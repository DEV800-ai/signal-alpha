"""Parse Form 4 (insider transaction) XML filings into sec_form4 table.

Source: SEC EDGAR Archives. Each Form 4 has a small XML doc with one or more
non-derivative transactions. We persist the structured fields and let the
signal layer filter to open-market purchases (transactionCode 'P').

Expensive — 38k+ filings × ~0.1s = ~70 min for a full backfill. Idempotent:
already-parsed accessions are skipped via the sec_form4 PRIMARY KEY.
"""
from __future__ import annotations

import time
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import signalalpha.edgar as _edgar
from tqdm import tqdm

from signalalpha.config import EDGAR_USER_AGENT
from signalalpha.db import connect

_session = requests.Session()
_session.headers.update({"User-Agent": EDGAR_USER_AGENT, "Accept-Encoding": "gzip, deflate"})


def _fetch_xml(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        with _edgar._lock:
            wait = _edgar._MIN_INTERVAL - (time.monotonic() - _edgar._last_request_at[0])
            if wait > 0:
                time.sleep(wait)
            _edgar._last_request_at[0] = time.monotonic()
        r = _session.get(url, timeout=30)
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429, 503):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    return None


def _filing_url(cik: str, accession: str, primary_doc: str) -> str:
    cik_int = int(cik)
    acc_nodash = accession.replace("-", "")
    doc = primary_doc.split("/", 1)[-1] if primary_doc.startswith("xsl") else primary_doc
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"


def _txt(node, *path) -> str | None:
    for p in path:
        node = node.find(p) if node is not None else None
    if node is None:
        return None
    # Many fields wrap their value in a <value> child
    val = node.find("value")
    if val is not None:
        return (val.text or "").strip() or None
    return (node.text or "").strip() or None


def parse_form4(xml_text: str) -> list[dict]:
    """Extract non-derivative transactions from a Form 4 XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    # Insider name / title
    insider_name = _txt(root, "reportingOwner", "reportingOwnerId", "rptOwnerName")
    rel = root.find("reportingOwner/reportingOwnerRelationship")
    title_parts: list[str] = []
    if rel is not None:
        for tag, label in [("isDirector", "Director"), ("isOfficer", "Officer"),
                           ("isTenPercentOwner", "10%Owner"), ("isOther", "Other")]:
            v = rel.find(tag)
            if v is not None and (v.text or "").strip().lower() in ("1", "true"):
                title_parts.append(label)
        ot = rel.find("officerTitle")
        if ot is not None:
            value = ot.find("value")
            if value is not None and value.text:
                title_parts.append(value.text.strip())
    insider_title = "; ".join(title_parts) or None

    txs = root.findall(".//nonDerivativeTransaction")
    out: list[dict] = []
    for t in txs:
        code = _txt(t, "transactionCoding", "transactionCode")
        date = _txt(t, "transactionDate")
        shares = _txt(t, "transactionAmounts", "transactionShares")
        price = _txt(t, "transactionAmounts", "transactionPricePerShare")
        if not code or not date:
            continue
        try:
            shares_f = float(shares) if shares else 0.0
            price_f = float(price) if price else 0.0
        except ValueError:
            continue
        out.append({
            "transaction_date": date,
            "transaction_code": code,
            "insider_name": insider_name or "UNKNOWN",
            "insider_title": insider_title,
            "shares": shares_f,
            "price_per_share": price_f,
            "transaction_usd": shares_f * price_f,
        })
    return out


def _already_parsed(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT DISTINCT accession FROM sec_form4").fetchall()}


def ingest_all(limit: int | None = None, since: str | None = None) -> int:
    con = connect()
    parsed = _already_parsed(con)
    sql = "SELECT ticker, cik, accession, filing_date, primary_doc FROM sec_filings WHERE form = '4'"
    params: list = []
    if since:
        sql += " AND filing_date >= ?"
        params.append(since)
    sql += " ORDER BY filing_date DESC"
    rows = con.execute(sql, params).fetchall()
    rows = [r for r in rows if r[2] not in parsed]
    if limit:
        rows = rows[:limit]
    inserted = 0
    failures = 0
    for ticker, cik, accession, filing_date, primary_doc in tqdm(rows, desc="Form 4"):
        url = _filing_url(cik, accession, primary_doc or "form4.xml")
        try:
            xml = _fetch_xml(url)
        except Exception:
            failures += 1
            continue
        if not xml:
            failures += 1
            continue
        txs = parse_form4(xml)
        if not txs:
            continue
        df = pd.DataFrame(txs)
        df.insert(0, "filing_date", filing_date)
        df.insert(0, "cik", cik)
        df.insert(0, "ticker", ticker)
        df.insert(0, "accession", accession)
        df = df.drop_duplicates(subset=["accession", "transaction_date",
                                        "transaction_code", "insider_name", "shares"])
        con.register("ftmp", df)
        con.execute(
            "INSERT OR IGNORE INTO sec_form4 "
            "(accession, ticker, cik, filing_date, transaction_date, transaction_code, "
            " insider_name, insider_title, shares, price_per_share, transaction_usd) "
            "SELECT accession, ticker, cik, filing_date, transaction_date, transaction_code, "
            "       insider_name, insider_title, shares, price_per_share, transaction_usd "
            "FROM ftmp"
        )
        con.unregister("ftmp")
        inserted += len(df)
    con.close()
    return inserted


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="Cap number of filings to parse (for testing)")
    args = p.parse_args()
    n = ingest_all(limit=args.limit)
    print(f"\nInserted {n:,} Form 4 transaction rows.")
