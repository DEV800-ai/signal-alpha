# Phase 3 — Step 1: Validator v1 implementation prompt

This is the prompt to use when implementing the Validator. It supersedes the earlier prompt that bundled Validator + Daily Signal Brief — the Daily Brief is split out because it depends on a `signal_firings` table that does not yet exist.

---

## Context

You are implementing **Validator v1** for SignalAlpha — the gate between draft and live wiki content.

The full architecture is in:
- `docs/llm-wiki-architecture.md`
- `schemas/VALIDATOR_RULES.md`     (authoritative — read this first)
- `schemas/CITATION_GRAMMAR.md`
- `schemas/COMPANY_SCHEMA.md`, `schemas/SECTOR_SCHEMA.md`, `schemas/SIGNAL_SCHEMA.md`
- `schemas/AGENTS.md`, `schemas/WIKI_UPDATE_RULES.md`

**You are implementing one component, not the system.** Daily Signal Brief is out of scope (it's the next prompt, after `signal_firings` is designed).

## Goal

A working Validator that:

1. Loads a wiki page from disk.
2. Runs Passes 1, 3, 4 (and a minimal Pass 2: required-section presence).
3. Returns a structured `ValidationResult`.
4. Has a CLI entry point.
5. Has unit tests against `docs/sample-pages/volume_anomaly.md` (PASS) plus three failure fixtures.

**No code outside the Validator. No LLM calls. Read-only over DuckDB and the wiki tree.**

## Repo layout (use exactly these paths)

The repo uses a `src/` layout. Place new code at:

```
src/signalalpha/wiki/
    __init__.py
    validate.py             # public entry point: validate(page_path, db) -> ValidationResult
    frontmatter.py          # Pass 1
    structure.py            # minimal Pass 2 (required sections in order)
    citations.py            # Pass 3
    claim_types.py          # Pass 4
    types.py                # ValidationResult dataclass + Failure/Warning shapes
    cli.py                  # `python -m signalalpha.wiki.validate` entry

tests/wiki/
    fixtures/
        volume_anomaly_pass.md         # copy of docs/sample-pages/volume_anomaly.md
        missing_citation_fail.md       # citation that won't resolve
        bad_uri_fail.md                # malformed citation URI
        lifecycle_integrity_fail.md    # lifecycle:reviewed + last_updated > last_reviewed
        unsupported_schema_fail.md     # schema_version > Validator.VERSION
    test_pass1_frontmatter.py
    test_pass2_structure.py
    test_pass3_citations.py
    test_pass4_claim_types.py
    test_validate_e2e.py
```

CLI invocation: `uv run python -m signalalpha.wiki.validate <page_path>`.

## Pass 1 — Frontmatter (full v1)

Required-field check is per page-type schema. Detect page type from the path:
- `wiki/companies/...`  → COMPANY_SCHEMA frontmatter
- `wiki/sectors/...`    → SECTOR_SCHEMA frontmatter
- `wiki/signals/...`    → SIGNAL_SCHEMA frontmatter
- `docs/sample-pages/<signal_or_ticker_name>.md` → infer by frontmatter shape (sample fixtures)

### Type checks

| Field | Check |
| --- | --- |
| `last_updated`, `last_reviewed` | parse as ISO date; reject if > today |
| `lifecycle` | enum: `draft` / `validated` / `reviewed` |
| `confidence` | enum: `low` / `medium` / `high` |
| `freshness_status` | enum: `current` / `stale` / `needs_review` |
| `status` (signal) | enum: `validated` / `borderline` / `graveyard` / `deprecated` |
| `schema_version` | integer in `[MIN_SUPPORTED_SCHEMA_VERSION, Validator.VERSION]` |
| `ticker` (when present) | exists in `data/universe.csv` |
| `sector` (when present) | exists in `data/universe.csv` |
| `code_version` (signal pages) | non-empty 7-char hex (git short-hash) |
| `data_sources` (signal pages) | each entry matches `^(db:[a-z_]+\|external:[a-z_-]+)$` |

### Lifecycle integrity (FAIL)

If `lifecycle == "reviewed"` AND `last_updated > last_reviewed` → **FAIL**.
Message: "page claims `lifecycle: reviewed` but `last_updated` (X) is after `last_reviewed` (Y); curator must re-review or demote lifecycle."

### Date discipline (do NOT do this in Pass 1)

The Validator does **not** check whether `last_updated` is "today if file changed." That comparison requires a notion of "previous version" the Validator does not have. Leave it to a pre-commit hook (separate work). Pass 1 only checks: ISO format, not-in-future, and `last_updated >= last_reviewed`.

### Schema-version compatibility

Constants:

```python
class Validator:
    VERSION = 1
    MIN_SUPPORTED_SCHEMA_VERSION = 1
```

- `schema_version < MIN_SUPPORTED` → FAIL ("page uses schema_version=N; this validator supports >=M; run `tools/migrate-page.py`").
- `schema_version > VERSION` → FAIL ("page uses schema_version=N; this validator supports up to M; upgrade the validator before merging this page").

## Pass 2 — Section structure (minimal v1)

Only one check: required sections from the page-type schema are present, in order. Section heading detection: H2 (`##`) headings, case-insensitive match on the section title (stripping the leading number and trailing parentheticals).

Auto-generated section markers (`<!-- AUTOGEN:BEGIN ... --> ... <!-- AUTOGEN:END ... -->`) are recognized as section content but their interior is NOT validated by Pass 2. Pass 2 only confirms the wrapping markers are paired. Mismatched / missing markers → FAIL.

Length budgets are NOT enforced in Pass 2 (deferred to Pass 6, which is out of v1 scope).

## Pass 3 — Citations (full v1)

### Disambiguation (per `CITATION_GRAMMAR.md`)

For every markdown link `[label](target)` in the body:

| Target shape | Treatment |
| --- | --- |
| `<scheme>:<entity_id>[#<fragment>]` where `<scheme>` is in the grammar | citation — Pass 3 |
| `<relative-path>.md[#<anchor>]` | wiki cross-link — skip in v1 (Pass 5 deferred) |
| `https://...` (no `web:` prefix) | informational — skip |
| anything else | ambiguous — Pass 3 FAIL with diagnostic |

### Per-citation checks

1. **Syntax.** URI must parse against the grammar. Per-scheme `entity_id` regex from the table in `CITATION_GRAMMAR.md` must match. FAIL on any deviation.
2. **Resolution.** Batched query per scheme:
   - Group all citations by scheme.
   - For each DB-backed scheme (`filing`, `tx`, `earnings`, `signal_run`, `price`): one `SELECT ... WHERE <pk> IN (...)` over the corresponding table.
   - For each external-table scheme (`news`, `transcript`, `patent`, `web`): one `SELECT ... WHERE source_uri IN (...)` over `sources`.
   - Any URI that didn't appear in the result set → FAIL.
3. **Naive per-row queries are forbidden.** A page with 50 citations must hit DB at most ~6 times (one per scheme present).

### What Pass 3 does NOT do

- Does not probe URLs for liveness.
- Does not check that the cited source supports the claim.
- Does not check that snapshot files exist on disk (deferred to Phase 5).
- Does not validate fragments (`#item-1.01`).

## Pass 4 — Claim types (full v1)

Defaults are declared per-section in each page-type schema. Inline override syntax (per `VALIDATOR_RULES.md`):

```markdown
<!-- claim_type: factual_claim -->
This paragraph is factual.

The next paragraph reverts to the section default.
```

Override scope ends at: blank line followed by next block, next override, or next H2/H3 heading.

### Citation-presence rule

| claim_type | Citation requirement |
| --- | --- |
| `factual_claim` | REQUIRED — at least one citation in the block |
| `signal_summary` | REQUIRED — at least one `signal_run:N` citation in the block |
| `private_company_context` | REQUIRED — at least one citation in the block |
| `interpretation` | optional — see nuance below |
| `risk_note` | optional |

### Interpretation nuance (per `VALIDATOR_RULES.md`)

A section whose default claim_type is `interpretation` does not need its own citations *if* there is at least one citation elsewhere in the same H2 section. If the entire section heading has zero citations → WARN (not FAIL).

**Refinement (curator request):** within an `interpretation` section, also WARN if a paragraph contains a quantitative assertion (regex: `\d+(\.\d+)?%` or `p\s*[<=]\s*\d`) with no citation in scope. This catches "earnings surprised by 30%" snuck into reasoning. False positives are acceptable for v1.

## ValidationResult shape

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class Issue:
    pass_num: int                    # 1, 2, 3, or 4
    rule: str                        # e.g. "citation.resolution"
    message: str
    location: str | None = None      # e.g. "section 5, row 3"

@dataclass(frozen=True)
class PassResult:
    pass_num: int
    failures: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()

@dataclass(frozen=True)
class ValidationResult:
    page: str
    verdict: Literal["PASS", "FAIL"]
    pass_results: tuple[PassResult, ...]
    failures: tuple[Issue, ...]      # flattened across passes (for backward-compat readers)
    warnings: tuple[Issue, ...]
```

`pass_results` is the per-pass breakdown the prompt review called out — both flattened lists are kept for ergonomic CLI output.

JSON serialization for the CLI:

```json
{
  "page": "docs/sample-pages/volume_anomaly.md",
  "verdict": "PASS",
  "pass_results": [
    {"pass_num": 1, "failures": [], "warnings": []},
    {"pass_num": 2, "failures": [], "warnings": []},
    {"pass_num": 3, "failures": [], "warnings": []},
    {"pass_num": 4, "failures": [], "warnings": []}
  ],
  "failures": [],
  "warnings": []
}
```

CLI exit code: 0 if PASS, 1 if FAIL.

## Tests (acceptance criteria)

Each test must use a fixture file in `tests/wiki/fixtures/`. The `volume_anomaly_pass.md` fixture is `docs/sample-pages/volume_anomaly.md` copied verbatim — keep them in sync (or symlink).

Required test cases:

| Test | Fixture | Expected verdict | Asserts |
| --- | --- | --- | --- |
| Pass-all | `volume_anomaly_pass.md` | PASS | `failures` empty |
| Missing citation | `missing_citation_fail.md` | FAIL | a Pass-3 `citation.resolution` failure |
| Bad URI | `bad_uri_fail.md` | FAIL | a Pass-3 `citation.syntax` failure |
| Lifecycle integrity | `lifecycle_integrity_fail.md` | FAIL | a Pass-1 `lifecycle.integrity` failure |
| Unsupported schema | `unsupported_schema_fail.md` | FAIL | a Pass-1 `schema_version.unsupported` failure |
| Interpretation nuance | inline (`interpretation_warn.md`) | PASS with WARN | warning is on Pass 4 |

DB fixture: a minimal in-memory DuckDB seeded with one row each in `signal_runs`, `sec_filings`, `earnings_events` to cover the citations in `volume_anomaly_pass.md`. Use `pytest` fixtures for setup.

Performance assertion: not a unit test gate. Add a `tests/wiki/test_perf.py` smoke timer that reports wall-clock for the pass-all fixture; flag in console output if > 500ms. **Do not fail CI on it** — fixture pages are too small to be representative.

## Out of scope (do not implement)

- Pass 5 (cross-links + namespace) — deferred to Step 2.
- Pass 6 (anti-patterns + length budgets) — deferred to Step 2.
- Daily Signal Brief — separate work-stream pending `signal_firings` schema.
- Auto-generator — separate work-stream.
- Researcher / Reporter — separate work-streams.
- Any LLM call.
- Any modification to `db.py`, `backtest.py`, signal modules, or DuckDB schema.

## Determinism

- Validator output for `(page_bytes, db_state)` MUST be byte-identical across runs.
- No timestamps in output messages.
- Iteration order over citations: page order (top-to-bottom).
- Iteration order over passes: 1 → 2 → 3 → 4 (a failure in Pass 1 still runs subsequent passes; we want the full picture in one run).

## Failure-message style

Every failure message includes (a) which rule failed, (b) the offending value, (c) what the curator should do. Example:

```
[Pass 1 / lifecycle.integrity] page claims lifecycle: reviewed but last_updated (2026-05-05) > last_reviewed (2026-04-22).
  Resolution: curator re-reviews and bumps last_reviewed, OR demotes lifecycle to validated/draft.
```

Avoid: "invalid frontmatter", "bad citation", or any message that doesn't tell the curator what to do.

## Deliverables

1. `src/signalalpha/wiki/` package with the modules listed above.
2. CLI: `uv run python -m signalalpha.wiki.validate <page>`.
3. Test suite under `tests/wiki/` with all six required tests passing.
4. Fixtures under `tests/wiki/fixtures/`.
5. Updated `pyproject.toml` if a new dep is needed (none anticipated — `pyyaml`, `duckdb`, `pytest` already present).

## Done means

- `uv run pytest tests/wiki/` passes.
- `uv run python -m signalalpha.wiki.validate docs/sample-pages/volume_anomaly.md` exits 0 and prints the PASS JSON.
- `uv run python -m signalalpha.wiki.validate tests/wiki/fixtures/missing_citation_fail.md` exits 1 and prints structured failures.
- No code outside `src/signalalpha/wiki/` and `tests/wiki/` was modified.

## Anti-instructions (don't do these)

- Don't add a Daily Signal Brief.
- Don't add CLI flags beyond `<page_path>` for v1. (Future: `--format=json|text`, `--strict-warnings`.)
- Don't pretty-print or color the CLI output. The CLI emits JSON. A human-friendly view is a separate concern.
- Don't auto-fix anything. The Validator is read-only.
- Don't add a "soft mode" / "warn-only mode" / config knob. v1 has one mode.
- Don't add caching. v1 cold-starts every invocation; cache is a Step-2 optimization if profiling demands it.

## When in doubt

Pick the simplest working option and write a one-line comment in the code citing which schema doc / rule the choice came from. Where the schemas don't say, the safer default is FAIL (with a clear message) over silent PASS.
