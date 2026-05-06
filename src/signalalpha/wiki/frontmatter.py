"""Pass 1 — Frontmatter validation."""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from signalalpha.wiki.types import Issue, PassResult

# ── Schema version constants (per phase-3-step-1-validator-prompt.md) ────────
VALIDATOR_VERSION = 1
MIN_SUPPORTED_SCHEMA_VERSION = 1

# ── Per-page-type required fields ─────────────────────────────────────────────
_COMMON = ["lifecycle", "last_updated", "last_reviewed", "freshness_status", "confidence", "schema_version"]

REQUIRED_FIELDS: dict[str, list[str]] = {
    "signal": [
        "signal_id", "status", "hold_days", "data_sources", "validated_run_id",
        "code_version", "event_max_date", *_COMMON,
    ],
    "company": ["name", "status", "sector", *_COMMON],
    "sector": ["sector_id", "name", "benchmark_etf", *_COMMON],
}

# ── Enum domains ──────────────────────────────────────────────────────────────
_LIFECYCLE = {"draft", "validated", "reviewed"}
_CONFIDENCE = {"low", "medium", "high"}
_FRESHNESS = {"current", "stale", "needs_review"}
_SIGNAL_STATUS = {"validated", "borderline", "graveyard", "deprecated"}
_DATA_SOURCE_RE = re.compile(r"^(db:[a-z_]+|external:[a-z_-]+)$")
_CODE_VERSION_RE = re.compile(r"^[0-9a-f]{7}$")


def _load_universe(universe_csv: Path) -> tuple[set[str], set[str]]:
    """Return (tickers, sectors) sets from universe.csv."""
    tickers: set[str] = set()
    sectors: set[str] = set()
    with open(universe_csv, newline="") as f:
        for row in csv.DictReader(f):
            tickers.add(row["ticker"])
            sectors.add(row["sector"])
    return tickers, sectors


def _parse_iso_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def run_pass1(
    page_path: Path,
    fm: dict,
    page_type: str,
    today: date,
    universe_csv: Path | None = None,
) -> PassResult:
    failures: list[Issue] = []
    warnings: list[Issue] = []

    if universe_csv is None:
        from signalalpha.config import UNIVERSE_CSV
        universe_csv = UNIVERSE_CSV

    tickers, sectors = _load_universe(universe_csv)
    required = REQUIRED_FIELDS.get(page_type, _COMMON)

    # ── Required field presence ───────────────────────────────────────────────
    for field in required:
        if field not in fm:
            failures.append(Issue(1, "frontmatter.required", f"Missing required field `{field}`."))

    # ── Schema version ────────────────────────────────────────────────────────
    sv = fm.get("schema_version")
    if sv is not None:
        try:
            sv_int = int(sv)
        except (ValueError, TypeError):
            failures.append(Issue(1, "schema_version.type", f"schema_version must be an integer; got {sv!r}."))
            sv_int = None

        if sv_int is not None:
            if sv_int < MIN_SUPPORTED_SCHEMA_VERSION:
                failures.append(Issue(
                    1, "schema_version.unsupported",
                    f"Page uses schema_version={sv_int}; this validator supports >={MIN_SUPPORTED_SCHEMA_VERSION}; "
                    f"run `tools/migrate-page.py`.",
                ))
            elif sv_int > VALIDATOR_VERSION:
                failures.append(Issue(
                    1, "schema_version.unsupported",
                    f"Page uses schema_version={sv_int}; this validator supports up to {VALIDATOR_VERSION}; "
                    f"upgrade the validator before merging this page.",
                ))

    # ── Date fields ───────────────────────────────────────────────────────────
    last_updated = last_reviewed = None

    for field in ("last_updated", "last_reviewed"):
        raw = fm.get(field)
        if raw is None:
            continue
        d = _parse_iso_date(raw)
        if d is None:
            failures.append(Issue(1, "frontmatter.date_format", f"`{field}` is not a valid ISO date; got {raw!r}."))
            continue
        if d > today:
            failures.append(Issue(
                1, "frontmatter.date_future",
                f"`{field}` ({d}) is in the future (today is {today}). "
                f"Resolution: set {field} to today or an earlier date.",
            ))
        if field == "last_updated":
            last_updated = d
        else:
            last_reviewed = d

    # ── Lifecycle integrity ───────────────────────────────────────────────────
    lifecycle = fm.get("lifecycle")
    if lifecycle is not None and lifecycle not in _LIFECYCLE:
        failures.append(Issue(
            1, "frontmatter.enum",
            f"`lifecycle` must be one of {sorted(_LIFECYCLE)}; got {lifecycle!r}.",
        ))

    if lifecycle == "reviewed" and last_updated is not None and last_reviewed is not None:
        if last_updated > last_reviewed:
            failures.append(Issue(
                1, "lifecycle.integrity",
                f"Page claims lifecycle: reviewed but last_updated ({last_updated}) is after "
                f"last_reviewed ({last_reviewed}). "
                f"Resolution: curator re-reviews and bumps last_reviewed, OR demotes lifecycle to validated/draft.",
            ))

    # ── Enum checks ───────────────────────────────────────────────────────────
    confidence = fm.get("confidence")
    if confidence is not None and confidence not in _CONFIDENCE:
        failures.append(Issue(
            1, "frontmatter.enum",
            f"`confidence` must be one of {sorted(_CONFIDENCE)}; got {confidence!r}.",
        ))

    freshness = fm.get("freshness_status")
    if freshness is not None and freshness not in _FRESHNESS:
        failures.append(Issue(
            1, "frontmatter.enum",
            f"`freshness_status` must be one of {sorted(_FRESHNESS)}; got {freshness!r}.",
        ))

    # ── Signal-specific checks ────────────────────────────────────────────────
    if page_type == "signal":
        status = fm.get("status")
        if status is not None and status not in _SIGNAL_STATUS:
            failures.append(Issue(
                1, "frontmatter.enum",
                f"`status` must be one of {sorted(_SIGNAL_STATUS)}; got {status!r}.",
            ))

        code_ver = fm.get("code_version")
        if code_ver is not None:
            if not _CODE_VERSION_RE.match(str(code_ver)):
                failures.append(Issue(
                    1, "frontmatter.code_version",
                    f"`code_version` must be a 7-character hex git short-hash; got {code_ver!r}.",
                ))

        data_sources = fm.get("data_sources")
        if data_sources is not None:
            if not isinstance(data_sources, list):
                failures.append(Issue(1, "frontmatter.data_sources", "`data_sources` must be a list."))
            else:
                for entry in data_sources:
                    if not _DATA_SOURCE_RE.match(str(entry)):
                        failures.append(Issue(
                            1, "frontmatter.data_sources",
                            f"data_sources entry {entry!r} must match `db:<table>` or `external:<source>`.",
                        ))

    # ── Ticker / sector universe checks ───────────────────────────────────────
    ticker = fm.get("ticker")
    if ticker is not None and str(ticker) not in tickers:
        failures.append(Issue(
            1, "frontmatter.universe",
            f"`ticker` {ticker!r} not found in data/universe.csv. "
            f"Resolution: add the ticker to universe.csv or correct the frontmatter.",
        ))

    sector = fm.get("sector")
    if sector is not None and str(sector) not in sectors:
        failures.append(Issue(
            1, "frontmatter.universe",
            f"`sector` {sector!r} not found in data/universe.csv. "
            f"Resolution: add the sector to universe.csv or correct the frontmatter.",
        ))

    return PassResult(1, tuple(failures), tuple(warnings))
