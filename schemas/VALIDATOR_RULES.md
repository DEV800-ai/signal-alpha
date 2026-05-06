# Validator rules

The Validator is the gate between **draft** and **live** wiki content. It runs before any draft becomes a candidate for curator review. **No interpretive judgment.** All checks are mechanical and deterministic: same draft + same DuckDB state → same verdict.

This doc consolidates the validator's responsibilities. Other schema docs reference this one by name.

## What the Validator checks

The Validator runs the following passes, in order. The first failure stops the draft from being produced — but all failures in a pass are reported, not just the first.

### Pass 1 — Frontmatter

- All required frontmatter fields present (per the page-type schema: `COMPANY_SCHEMA.md`, `SECTOR_SCHEMA.md`, `SIGNAL_SCHEMA.md`).
- Values pass type checks:
  - `last_updated`, `last_reviewed` parse as ISO date.
  - `lifecycle`, `freshness_status`, `confidence`, `status` (where applicable) use only listed enum values.
  - `sector` exists in `data/universe.csv`.
  - `ticker` (when present) exists in `data/universe.csv`.

**Date-field discipline (load-bearing):**

| Field | Set by | When |
| --- | --- | --- |
| `last_updated` | Validator (or Researcher pre-commit) | Today if any page content changed since the previous version on disk. **FAIL** if the page body is modified but `last_updated` is not today. |
| `last_reviewed` | **Curator only** | When the curator reads the page and confirms it still reflects reality. Validator MUST NOT modify this field. |

The Validator may emit a WARN when `last_reviewed` is more than 90 days behind `last_updated` (the page has been mechanically touched without a freshness review), but it does not change the field.

**Schema versioning:**

The Validator declares a `Validator.VERSION` constant and a `MIN_SUPPORTED_SCHEMA_VERSION`.

- If page `schema_version ∈ [MIN_SUPPORTED, Validator.VERSION]` → validate normally.
- If page `schema_version < MIN_SUPPORTED` → FAIL with a clear migration message ("page uses schema_version=0; this validator supports >=1; run `tools/migrate-page.py`").
- If page `schema_version > Validator.VERSION` → FAIL ("page uses schema_version=N; this validator only supports up to M; upgrade the validator before merging this page").

This makes "validator and pages drift apart" a noisy failure, never a silent one.

### Pass 2 — Section structure

**FAIL conditions (hard):**

- All required sections present, in the order defined by the schema.
- Auto-generated sections are not edited by hand (detected via marker/checksum to be defined in Phase 3).
- Tables in catalyst / signal-history sections have all required columns.

**Moved to Pass 6 as WARN (not FAIL):**

- Section length budgets (e.g., `Strategic position ≤ 80 words`, `Bull case ≤ 3 bullets`). Hard caps cause unnatural writing and draft churn; budgets are a guideline, not a contract.

### Pass 3 — Citations

For every citation URI in the page body:

1. **Syntax.** URI parses against the grammar in `CITATION_GRAMMAR.md`.
2. **Resolution.** The entity exists in the appropriate target:
   - DuckDB-backed schemes (`filing`, `tx`, `earnings`, `signal_run`, `price`) → exact lookup.
   - External schemes (`news`, `transcript`, `patent`, `web`) → row in `sources` table with matching `source_uri`.
3. **Stability.** The cited row exists; its primary key has not changed since the citation was written. The "no-deletion of cited rows" rule is **DB policy**, not a Validator concern — the Validator can only check what's currently in the DB.

**Performance:**

- Citations are validated by **batched lookups per scheme**: one SQL query per scheme using an `IN (...)` clause over all URIs of that scheme on the page. Naive per-citation queries are not allowed in the implementation.
- A page with > 100 citations triggers a WARN (Pass 6). The hard ceiling exists to make pathological pages visible — it is not a structural failure.

The Validator does NOT:
- Probe URLs for liveness (out of scope — would slow drafts).
- Verify the cited source actually supports the claim (curator's job — the Validator is mechanical).
- Inspect snapshot file integrity.

### Pass 4 — Claim types

Every section has a default `claim_type` declared in its schema doc. Inline overrides use an HTML comment on its own line, immediately preceding the block (paragraph, list, or table) it applies to:

```markdown
<!-- claim_type: factual_claim -->
Intel reported $4.1B in foundry revenue [Q1 2026 release](earnings:INTC:2026-04-24).
```

**Override scope:** the override applies until the next of:
- a blank line followed by the next paragraph/list/table block,
- another `<!-- claim_type: ... -->` override,
- the next H2 or H3 heading.

A section's default applies otherwise. Unknown claim_type values FAIL Pass 4.

The Validator applies the **citation-presence rule** based on claim type:

| Claim type | Citation requirement | Rationale |
| --- | --- | --- |
| `factual_claim` | **REQUIRED** | Verifiable assertions of fact must be traceable. |
| `signal_summary` | **REQUIRED** — `signal_run:N` | Auto-generated content must cite its source row. |
| `private_company_context` | **REQUIRED** | Higher bar because no SEC filings are available. Must cite news / press / primary source. |
| `interpretation` | OPTIONAL — see "interpretation nuance" below. | Synthesis is allowed without citation, but unsupported synthesis is suspect. |
| `risk_note` | OPTIONAL — encouraged for external-trigger watch items. | Concrete watch-list items don't always have a single source; analytical risks may be inferential. |

A claim_type override applies to its block per the scope rules above. Section-level defaults apply otherwise.

**Interpretation nuance (v1):**

A section whose default claim_type is `interpretation` is allowed to have no citations of its own *if* there are citations earlier in the same section heading. Concretely:

- For each `interpretation` section, scan the immediately preceding bullets/paragraphs **within the same H2 (or H3) heading** for any citation URIs.
- If at least one citation exists in that nearby context → no WARN. The section is interpreting cited material, which is allowed.
- If the entire section heading contains zero citations → WARN.

**v1 limitation noted:** "nearby" is defined narrowly as same-section. Cross-section context (e.g., "interpretation in Section 4 implicitly references the catalyst table in Section 5") is not tracked. This will produce occasional false-positive WARNs; curator dismisses them. Lift this limitation only if the false-positive rate becomes a real cost.

### Pass 5 — Namespace and cross-link integrity

- **Public/private separation:**
  - A page in `wiki/companies/public/...` cannot have `status: private` in frontmatter.
  - A page in `wiki/companies/private/...` cannot have `status: public`.
  - Cross-links between public and private pages are allowed; the Validator only enforces that the link target exists.
- **Sector references:**
  - A `sector` value in frontmatter must match a sector page that exists.
- **Wiki cross-links:**
  - Every internal markdown link to another wiki page must resolve to a file that exists, after path normalization.

**Cross-link path normalization (v1):**

Before checking existence, the Validator normalizes a link target:

1. Strip URI fragment (`#section-id`) — fragment validity is not checked in v1.
2. Strip query string (`?foo=bar`) — wiki paths don't use them.
3. If the path starts with `/`, treat it as repo-root-absolute.
4. If the path is relative, resolve relative to the page's own directory.
5. Reject paths that escape the wiki tree (`../../etc/passwd`-style traversal) — FAIL with a security warning.
6. Treat paths as **case-sensitive** (POSIX). On case-insensitive filesystems the Validator still enforces case to keep the wiki portable.

Page renames are out of scope for the Validator — they're a curator concern handled by `git mv` + a search/replace pass.

### Pass 6 — Anti-pattern checks

**These rules are heuristic, best-effort, and explicitly tolerate false positives.** They are not authoritative — they prompt the curator to look at a section, nothing more. Curator can dismiss WARNs (they still appear in the audit log).

The pattern set is small **on purpose**. New patterns are added only if:
1. A real wiki page produced a problem the curator wanted the Validator to catch, and
2. A unit test demonstrates the pattern has a low false-positive rate on existing pages.

**v1 patterns:**

- Section starts with "Many analysts believe..." with no citation → WARN.
- Buy/sell/hold language detected ("buy here", "looks attractive", "selling at this level") → WARN.
- Price targets detected ("$XX by year-end") → WARN.
- More than 3 consecutive sentences without any citation in a `factual_claim` section → WARN.
- Future-tense forecast without a citation ("will be", "is going to") → WARN.
- **`web:` scheme overuse:** more than 20% of citations on a page use the `web:` scheme → WARN. Forces gradual migration to typed schemes (`news:`, `transcript:`, etc.).

**Moved here from Pass 2 (now WARN, not FAIL):**

- Section length budgets — `Strategic position > 80 words`, `Bull case > 3 bullets`, etc.
- Page has > 100 citation URIs.

**Hard rule:** the v1 pattern list does not grow without a curator-approved PR + test. Resist the urge to add "smart" detection — the value of this pass is *signal-to-noise of warnings*, not coverage.

## Output format

The Validator returns a structured result:

```json
{
  "page": "wiki/companies/public/INTC.md",
  "verdict": "PASS" | "FAIL",
  "failures": [
    { "pass": 3, "rule": "citation.resolution",
      "message": "filing:0001234567-26-000001 not found in sec_filings",
      "location": "section 5, row 3" }
  ],
  "warnings": [
    { "pass": 6, "rule": "anti_pattern.unsourced_synthesis",
      "message": "3 consecutive sentences without citation",
      "location": "section 4" }
  ]
}
```

A draft can be produced if and only if `verdict == "PASS"`. Warnings do not block; they appear in the curator's review.

## Lifecycle states

Three orthogonal frontmatter fields describe a page's standing. They live alongside the existing entity-type `status` (public/private/delisted in COMPANY_SCHEMA — unrelated to lifecycle).

| Field | Domain | Set by | Meaning |
| --- | --- | --- | --- |
| `lifecycle` | `draft` / `validated` / `reviewed` | mixed | workflow position |
| `confidence` | `low` / `medium` / `high` | curator | how well-sourced the curator considers the page |
| `freshness_status` | `current` / `stale` / `needs_review` | derived from `last_reviewed`, override allowed | timing |

**Lifecycle transitions (Validator-relevant):**

- `draft` → `validated`: Validator passes. Mechanical. Validator may set this transition automatically when a draft passes.
- `validated` → `reviewed`: **curator-only.** The Validator never makes this transition. The curator sets `lifecycle: reviewed` after reading and accepting the page.
- Any → `draft`: any meaningful body change demotes the page. The Validator enforces "if body content changed, `lifecycle` must be `draft` until re-validated."

**Lifecycle integrity rule (FAIL):**

If `lifecycle == reviewed` AND `last_updated > last_reviewed`, the page is in a misleading state — it claims curator review but has been mechanically modified since. The Validator FAILs the page in this case. Resolution is one of:

1. Curator re-reviews and bumps `last_reviewed` to today, OR
2. Page is demoted to `lifecycle: validated` (or `draft`) by the curator, OR
3. The body change is reverted.

This rule is the load-bearing piece that prevents lifecycle from being a false advertisement.

**Why three fields instead of one:**

- Lifecycle answers "is it live?"
- Confidence answers "how good is it?"
- Freshness answers "is it current?"

A page can be `lifecycle: reviewed`, `confidence: low`, `freshness_status: stale` — fully orthogonal. Daily-report rendering (Phase 5) decides what to show based on the combination.

## Implementation contract (Phase 3)

### Phase 3 — Step 1 (v1 scope)

Per curator scope decision: implement only the **highest-value passes** end-to-end before adding the rest.

**v1 scope:**

| Pass | v1 status |
| --- | --- |
| 1 — Frontmatter | **YES** — required field check, type check, date-field discipline (`last_updated` vs `last_reviewed`), schema-version compatibility |
| 2 — Section structure | minimal — required sections present, in order. **Skip** auto-generated section markers in v1 (Phase 3 Step 2). |
| 3 — Citations | **YES** — full (syntax + resolution + batched lookups + stability) |
| 4 — Claim types | **YES** — full (citation-presence per type + interpretation nuance) |
| 5 — Namespace + cross-links | **SKIP in v1** — re-enable in Step 2 after the first real pages exist |
| 6 — Anti-patterns | **SKIP in v1** — re-enable in Step 2 once the false-positive rate can be measured against real pages |

**v1 entry point:**

```python
def validate(page_path: Path, db: duckdb.DuckDBPyConnection) -> ValidationResult:
    # v1: passes 1, (minimal) 2, 3, 4 only
```

CLI:

```
uv run python -m signalalpha.wiki.validate <page>
```

### v1 acceptance criteria

- Passes 1, 3, 4 implemented per the contracts above.
- Pass 2 implements only the "required sections present in order" check; auto-generated-section detection deferred.
- Each implemented pass has unit tests with at least one passing case and one failing case.
- The Validator runs against a hand-written fixture (e.g., `tests/fixtures/wiki/companies/public/NVDA_minimal.md`) and produces a sensible PASS or FAIL with structured failures.
- Output JSON matches the format below.
- Total Validator runtime on a 50-citation page: < 200ms wall clock (with batched DB lookups).

### Phase 3 — Step 2 (after Step 1 ships)

Add Pass 5 (cross-links + namespace) and Pass 6 (anti-patterns + length budgets) once Step 1 is in production and the fixture page set is large enough to measure false-positive rates.

## Stability rules

- Existing passes never have their semantics weakened. New passes can be added; old passes can be tightened only with explicit version bump.
- The output JSON schema is versioned. Older Validator output remains parseable.
- Warnings can graduate to failures only with a schema_version bump and migration of existing pages.

## Anti-patterns (validator design)

- **Validator as judge of truth.** The Validator never decides if a claim is correct — it only decides if the claim is *cited and structured correctly*. Truth is the curator's call.
- **Validator that calls LLMs.** Mechanical only. Any LLM-based check belongs to a separate quality-bar agent, not this one.
- **Validator that mutates state.** Read-only over DuckDB and the wiki tree. The only thing it returns is a verdict + list of issues.
