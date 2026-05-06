"""Pass 3 — Citations: syntax + batched resolution."""
from __future__ import annotations

import re
from collections import defaultdict

import duckdb

from signalalpha.wiki.types import Issue, PassResult

# ── Link extraction ───────────────────────────────────────────────────────────
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

KNOWN_SCHEMES = frozenset(
    ["filing", "tx", "earnings", "signal_run", "price", "news", "transcript", "patent", "web"]
)

# ── Per-scheme entity_id regexes (from CITATION_GRAMMAR.md) ──────────────────
_ENTITY_RE: dict[str, re.Pattern] = {
    "filing":     re.compile(r"^\d{10}-\d{2}-\d{6}$"),
    "tx":         re.compile(r"^\d{10}-\d{2}-\d{6}:\d+$"),
    "earnings":   re.compile(r"^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$"),
    "signal_run": re.compile(r"^\d+$"),
    "price":      re.compile(r"^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$"),
    "news":       re.compile(r"^[a-z][a-z0-9_]*/\d{4}-\d{2}-\d{2}/[a-z0-9-]+$"),
    "transcript": re.compile(r"^[A-Z]{1,5}:\d{4}-Q[1-4]$|^[A-Z]{1,5}:\d{4}-\d{2}-\d{2}$"),
    "patent":     re.compile(r"^(US|WO|EP)-[A-Z0-9-]+$"),
    "web":        re.compile(r"^https?://"),
}

# DB-backed schemes: table and column to match against.
_DB_SCHEMES: dict[str, tuple[str, str]] = {
    "signal_run": ("signal_runs", "run_id"),
    "filing":     ("sec_filings", "accession"),
}
# Schemes that resolve via sources table.
_SOURCES_SCHEMES = frozenset(["news", "transcript", "patent", "web"])
# Schemes with composite keys resolved separately.
_COMPOSITE_SCHEMES = frozenset(["tx", "earnings", "price"])


def _classify(target: str) -> str:
    """Return 'citation', 'cross-link', 'external', or 'ambiguous'."""
    base = target.split("#")[0]
    if base.startswith("http://") or base.startswith("https://"):
        return "external"
    if base.endswith(".md"):
        return "cross-link"
    if ":" in base:
        scheme = base.split(":")[0]
        if scheme in KNOWN_SCHEMES:
            return "citation"
    return "ambiguous"


def _extract_citations(body: str) -> list[tuple[str, str, str]]:
    """Return list of (label, target_without_fragment, full_target)."""
    results = []
    for label, target in _LINK_RE.findall(body):
        kind = _classify(target)
        if kind == "citation":
            base = target.split("#")[0]
            results.append((label, base, target))
    return results


def _resolve_signal_run(ids: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    run_ids = [int(i) for i in ids]
    placeholders = ", ".join("?" * len(run_ids))
    rows = db.execute(
        f"SELECT run_id::text FROM signal_runs WHERE run_id IN ({placeholders})", run_ids
    ).fetchall()
    return {r[0] for r in rows}


def _resolve_filing(ids: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    placeholders = ", ".join("?" * len(ids))
    rows = db.execute(
        f"SELECT accession FROM sec_filings WHERE accession IN ({placeholders})", ids
    ).fetchall()
    return {r[0] for r in rows}


def _resolve_tx(entity_ids: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    """Check that the accession part of tx:<accession>:<index> exists in sec_form4."""
    accessions = list({eid.rsplit(":", 1)[0] for eid in entity_ids})
    placeholders = ", ".join("?" * len(accessions))
    rows = db.execute(
        f"SELECT DISTINCT accession FROM sec_form4 WHERE accession IN ({placeholders})", accessions
    ).fetchall()
    found_accessions = {r[0] for r in rows}
    # Return entity_ids whose accession was found.
    return {eid for eid in entity_ids if eid.rsplit(":", 1)[0] in found_accessions}


def _resolve_earnings(entity_ids: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    """entity_id is TICKER:YYYY-MM-DD."""
    pairs = [eid.split(":", 1) for eid in entity_ids]
    conditions = " OR ".join(
        f"(ticker = ? AND date(event_date)::text = ?)" for _ in pairs
    )
    params = [x for pair in pairs for x in pair]
    rows = db.execute(
        f"SELECT ticker, date(event_date)::text FROM earnings_events WHERE {conditions}",
        params,
    ).fetchall()
    return {f"{r[0]}:{r[1]}" for r in rows}


def _resolve_price(entity_ids: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    """entity_id is TICKER:YYYY-MM-DD."""
    pairs = [eid.split(":", 1) for eid in entity_ids]
    conditions = " OR ".join(
        f"(ticker = ? AND date::text = ?)" for _ in pairs
    )
    params = [x for pair in pairs for x in pair]
    rows = db.execute(
        f"SELECT ticker, date::text FROM prices WHERE {conditions}", params
    ).fetchall()
    return {f"{r[0]}:{r[1]}" for r in rows}


def _resolve_sources(uris: list[str], db: duckdb.DuckDBPyConnection) -> set[str]:
    """Resolve external-scheme citations via the sources table."""
    placeholders = ", ".join("?" * len(uris))
    try:
        rows = db.execute(
            f"SELECT source_uri FROM sources WHERE source_uri IN ({placeholders})", uris
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        # sources table may not exist yet; treat all as unresolved.
        return set()


def run_pass3(body: str, db: duckdb.DuckDBPyConnection) -> PassResult:
    failures: list[Issue] = []
    warnings: list[Issue] = []

    # ── Ambiguous link detection ──────────────────────────────────────────────
    for _, target in _LINK_RE.findall(body):
        kind = _classify(target)
        if kind == "ambiguous":
            failures.append(Issue(
                3, "citation.ambiguous",
                f"Link target {target!r} is ambiguous — not a citation URI, wiki cross-link (.md), "
                f"or plain external URL (https://). "
                f"Resolution: use a citation scheme (e.g., web:https://...) or a .md relative path.",
            ))

    # ── Collect all citations ─────────────────────────────────────────────────
    citation_list = _extract_citations(body)
    if not citation_list:
        return PassResult(3, tuple(failures), tuple(warnings))

    # ── Syntax check (per-scheme regex) ──────────────────────────────────────
    by_scheme: dict[str, list[str]] = defaultdict(list)
    syntax_bad: set[str] = set()

    for _label, base, _full in citation_list:
        scheme, _, entity_id = base.partition(":")
        pattern = _ENTITY_RE.get(scheme)
        if pattern is None:
            # Unknown scheme should have been caught by _classify, but guard anyway.
            failures.append(Issue(3, "citation.syntax",
                f"Unknown citation scheme '{scheme}' in '{base}'."))
            syntax_bad.add(base)
            continue
        if not pattern.match(entity_id):
            failures.append(Issue(
                3, "citation.syntax",
                f"Citation '{base}' has invalid entity_id for scheme '{scheme}'. "
                f"Expected pattern: {pattern.pattern}. "
                f"Resolution: correct the citation URI to match the required format.",
            ))
            syntax_bad.add(base)
        else:
            by_scheme[scheme].append(entity_id)

    # De-duplicate per scheme (batch queries).
    by_scheme = {s: list(dict.fromkeys(ids)) for s, ids in by_scheme.items()}

    # ── Resolution (batched per scheme) ──────────────────────────────────────
    resolved: dict[str, set[str]] = {}

    if "signal_run" in by_scheme:
        resolved["signal_run"] = _resolve_signal_run(by_scheme["signal_run"], db)
    if "filing" in by_scheme:
        resolved["filing"] = _resolve_filing(by_scheme["filing"], db)
    if "tx" in by_scheme:
        resolved["tx"] = _resolve_tx(by_scheme["tx"], db)
    if "earnings" in by_scheme:
        resolved["earnings"] = _resolve_earnings(by_scheme["earnings"], db)
    if "price" in by_scheme:
        resolved["price"] = _resolve_price(by_scheme["price"], db)

    external_uris = []
    for scheme in _SOURCES_SCHEMES:
        if scheme in by_scheme:
            for eid in by_scheme[scheme]:
                external_uris.append(f"{scheme}:{eid}")
    if external_uris:
        found = _resolve_sources(external_uris, db)
        for uri in external_uris:
            scheme = uri.split(":")[0]
            resolved.setdefault(scheme, set())
            if uri in found:
                resolved[scheme].add(uri.split(":", 1)[1])

    # ── Report unresolved citations (in page order) ───────────────────────────
    for _label, base, _full in citation_list:
        if base in syntax_bad:
            continue
        scheme, _, entity_id = base.partition(":")
        if scheme in _SOURCES_SCHEMES:
            # For external schemes, we stored full URI; check entity_id presence differently.
            full_uri = base
            found_set = resolved.get(scheme, set())
            if entity_id not in found_set:
                failures.append(Issue(
                    3, "citation.resolution",
                    f"Citation '{base}' not found in sources table. "
                    f"Resolution: add a row to the sources table with source_uri='{base}'.",
                ))
        else:
            found_set = resolved.get(scheme, set())
            if entity_id not in found_set:
                table_map = {
                    "signal_run": "signal_runs",
                    "filing": "sec_filings",
                    "tx": "sec_form4",
                    "earnings": "earnings_events",
                    "price": "prices",
                }
                table = table_map.get(scheme, scheme)
                failures.append(Issue(
                    3, "citation.resolution",
                    f"Citation '{base}' not found in {table}. "
                    f"Resolution: verify the entity_id is correct and the row exists in the database.",
                ))

    return PassResult(3, tuple(failures), tuple(warnings))
