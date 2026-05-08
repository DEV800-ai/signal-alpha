"""Fetch granted patents from PatentsView S3 bulk files (no auth required).

Downloads two bulk TSV snapshots once and caches them locally:
  - g_patent.tsv.zip                  (~230 MB compressed)
  - g_assignee_disambiguated.tsv.zip  (~360 MB compressed)

Re-downloads only when the S3 Last-Modified header is newer than the cache.
Idempotent: patent_id is the PRIMARY KEY, so re-runs are safe.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request
import zipfile
from dataclasses import dataclass, field

import pandas as pd

from signalalpha.config import DATA_DIR
from signalalpha.db import connect

S3_BASE = "https://s3.amazonaws.com/data.patentsview.org/download"
PATENT_ZIP   = "g_patent.tsv.zip"
ASSIGNEE_ZIP = "g_assignee_disambiguated.tsv.zip"
BULK_DIR     = DATA_DIR / "patent_bulk"
ASSIGNEES_CSV = DATA_DIR / "patent_assignees.csv"
HISTORY_START = "2018-01-01"


@dataclass
class PatentIngestStats:
    rows_inserted: int = 0
    last_date: dt.date | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _s3_last_modified(filename: str) -> str:
    req = urllib.request.Request(f"{S3_BASE}/{filename}", method="HEAD")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.headers.get("Last-Modified", "")


def _is_stale(filename: str) -> bool:
    local = BULK_DIR / filename
    meta  = local.with_suffix(".meta.json")
    if not local.exists() or not meta.exists():
        return True
    cached_lm = json.loads(meta.read_text()).get("last_modified", "")
    return _s3_last_modified(filename) != cached_lm


def _download(filename: str) -> None:
    local = BULK_DIR / filename
    url   = f"{S3_BASE}/{filename}"
    print(f"    Downloading {filename} …", end=" ", flush=True)
    urllib.request.urlretrieve(url, local)
    lm = _s3_last_modified(filename)
    local.with_suffix(".meta.json").write_text(json.dumps({"last_modified": lm}))
    print(f"{local.stat().st_size / 1e6:.0f} MB OK")


def _ensure_bulk_files() -> tuple:
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    for filename in (PATENT_ZIP, ASSIGNEE_ZIP):
        if _is_stale(filename):
            _download(filename)
        else:
            print(f"    {filename}: cached and current")
    return BULK_DIR / PATENT_ZIP, BULK_DIR / ASSIGNEE_ZIP


# ---------------------------------------------------------------------------
# Column detection helpers (schema varies across PatentsView releases)
# ---------------------------------------------------------------------------

def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    # Try case-insensitive
    lower_map = {col.lower(): col for col in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


# ---------------------------------------------------------------------------
# Core data loading
# ---------------------------------------------------------------------------

def _load_patents(
    patent_zip: object,
    assignee_zip: object,
    company_map: dict[str, str],   # lower(assignee_query) -> ticker
) -> pd.DataFrame:
    """
    Two-pass load:
      1. Scan assignee file → build {patent_id: (ticker, assignee_name)}
      2. Scan patent file   → keep rows where patent_id in step-1 set and date >= HISTORY_START
    """
    # ---- Pass 1: assignee file ----------------------------------------
    print("    Scanning assignee file for matching companies …", end=" ", flush=True)
    patent_to_info: dict[str, dict] = {}

    with zipfile.ZipFile(assignee_zip) as zf:
        tsv_name = zf.namelist()[0]
        with zf.open(tsv_name) as f:
            first_chunk = True
            org_col = id_col = None
            for chunk in pd.read_csv(f, sep="\t", chunksize=200_000,
                                     dtype=str, low_memory=False):
                if first_chunk:
                    org_col = _find_col(chunk, [
                        "disambig_assignee_organization",
                        "organization",
                        "assignee_organization",
                    ])
                    id_col = _find_col(chunk, ["patent_id", "patentId"])
                    if not org_col or not id_col:
                        raise RuntimeError(
                            f"Cannot find required columns. Got: {list(chunk.columns)}"
                        )
                    first_chunk = False

                chunk = chunk.dropna(subset=[org_col, id_col])
                orgs_lower = chunk[org_col].str.lower()

                for query_lower, ticker in company_map.items():
                    mask = orgs_lower.str.contains(query_lower, regex=False, na=False)
                    for _, row in chunk[mask].iterrows():
                        pid = row[id_col]
                        if pid not in patent_to_info:
                            patent_to_info[pid] = {
                                "ticker":        ticker,
                                "assignee_name": row[org_col],
                            }

    print(f"{len(patent_to_info):,} matching patent IDs found")

    if not patent_to_info:
        return pd.DataFrame(columns=["patent_id", "grant_date", "ticker", "assignee_name"])

    matching_ids = set(patent_to_info.keys())

    # ---- Pass 2: patent file ------------------------------------------
    print("    Scanning patent file for grant dates …", end=" ", flush=True)
    rows: list[dict] = []

    with zipfile.ZipFile(patent_zip) as zf:
        tsv_name = zf.namelist()[0]
        with zf.open(tsv_name) as f:
            first_chunk = True
            date_col = id_col2 = None
            for chunk in pd.read_csv(f, sep="\t", chunksize=200_000,
                                     dtype=str, low_memory=False):
                if first_chunk:
                    date_col = _find_col(chunk, ["patent_date", "date", "grantDate"])
                    id_col2  = _find_col(chunk, ["patent_id", "patentId"])
                    if not date_col or not id_col2:
                        raise RuntimeError(
                            f"Cannot find required columns. Got: {list(chunk.columns)}"
                        )
                    first_chunk = False

                sub = chunk[chunk[id_col2].isin(matching_ids)].copy()
                sub = sub.dropna(subset=[date_col])
                sub = sub[sub[date_col] >= HISTORY_START]

                for _, row in sub.iterrows():
                    pid = row[id_col2]
                    info = patent_to_info[pid]
                    rows.append({
                        "patent_id":     pid,
                        "grant_date":    row[date_col],
                        "ticker":        info["ticker"],
                        "assignee_name": info["assignee_name"],
                    })

    print(f"{len(rows):,} rows in date range")
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["patent_id", "grant_date", "ticker", "assignee_name"]
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ingest_all() -> list[PatentIngestStats]:
    if not ASSIGNEES_CSV.exists():
        raise FileNotFoundError(f"Patent assignees mapping not found: {ASSIGNEES_CSV}")

    print("  Ensuring PatentsView bulk files are cached …")
    try:
        patent_zip, assignee_zip = _ensure_bulk_files()
    except Exception as e:
        stats = PatentIngestStats(errors=[str(e)])
        print(f"  ERROR downloading bulk files: {e}")
        return [stats]

    assignees_df = pd.read_csv(ASSIGNEES_CSV)
    company_map  = {
        row["assignee_query"].lower(): row["ticker"]
        for _, row in assignees_df.iterrows()
    }

    print("  Processing bulk files …")
    try:
        df = _load_patents(patent_zip, assignee_zip, company_map)
    except Exception as e:
        stats = PatentIngestStats(errors=[str(e)])
        print(f"  ERROR processing bulk files: {e}")
        return [stats]

    if df.empty:
        print("  No matching rows found.")
        return [PatentIngestStats()]

    df["grant_date"] = pd.to_datetime(df["grant_date"], errors="coerce").dt.date
    df = df.dropna(subset=["grant_date"])

    con = connect(read_only=False)
    con.execute("""
        INSERT OR IGNORE INTO patents (patent_id, grant_date, ticker, assignee_name)
        SELECT patent_id, grant_date::DATE, ticker, assignee_name
        FROM df
    """)
    con.close()

    stats = PatentIngestStats(
        rows_inserted=len(df),
        last_date=df["grant_date"].max(),
    )
    print(f"  Inserted {stats.rows_inserted:,} rows (last grant: {stats.last_date})")
    return [stats]


if __name__ == "__main__":
    print("Ingesting granted patents from PatentsView S3 bulk files …")
    results = ingest_all()
    total  = sum(r.rows_inserted for r in results)
    errors = [e for r in results for e in r.errors]
    print(f"\nDone. {total:,} rows inserted. {len(errors)} errors.")
