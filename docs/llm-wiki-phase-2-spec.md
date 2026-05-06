# Phase 2 spec — Source-ingestion metadata model

Status: **proposal — no code yet.**
Predecessor: Phase 1 (six schema docs) — must be reviewed and accepted before this lands.

## Phase boundary (explicit)

| Phase | Scope | Deliverable |
| --- | --- | --- |
| Phase 2 | **Spec only** | Design docs + grammar + DDL on paper |
| Phase 3 | **Implementation** | Validator skeleton + `sources` table created in DuckDB + Researcher pipeline |

Phase 2 ends when the curator approves the design. Phase 3 cannot begin until Phase 2 is closed.

## Goal

Make the wiki's claim-to-source links (citations) into a **machine-checkable contract**. When a wiki page says *"Intel announced an ARM design partnership [filing:1234567]"*, the system must be able to:

1. Verify that `filing:1234567` resolves to a real, retrievable source.
2. Render the citation as a working link in the daily report.
3. Refuse to ship a page if any citation fails to resolve.

Phase 2 produces the **specification + minimal data model** to support this. Implementation lives in Phase 3.

## What's in scope (Phase 2 spec — docs only)

- The **citation URI grammar** — what `filing:...`, `tx:...`, `news:...` etc. look like.
- The **resolution rules** — which DuckDB table or external store each scheme maps to.
- The **`sources` table** — the one new DuckDB addition needed for external citations (news, transcripts).
- The **Validator's resolution algorithm** — how it checks a draft's citations.
- The **stability contract** — what must never change once a citation key is published.

## What's out of scope (deferred to later phases)

- Phase 3 — actually wiring up the Researcher / Validator to use these contracts.
- News / transcript ingestion — Phase 2 specifies the schema; ingestion is its own work.
- Patent ingestion (USPTO) — same.
- LLM-content hallucination defenses — orthogonal problem; covered by curator review.
- Full-text search over sources — defer until needed.

## Citation URI grammar (summary)

```
<scheme>:<entity_id>[#<fragment>]
```

Schemes mapped today:

| Scheme | Resolves to | Example |
| --- | --- | --- |
| `filing:` | `sec_filings.accession` | `filing:0001127602-26-018000#item-1.01` |
| `tx:` | `sec_form4` composite key | `tx:0001127602-26-018000:0` (transaction index) |
| `earnings:` | `earnings_events` | `earnings:INTC:2026-04-24` |
| `signal_run:` | `signal_runs.run_id` | `signal_run:2` |
| `price:` | `prices` (ticker, date) | `price:NVDA:2024-01-03` |
| `news:` | `sources` table (external) | `news:reuters/2026-04-19/intel-arm-deal` |
| `transcript:` | `sources` table (external) | `transcript:INTC:2026-Q1#p4` |
| `patent:` | `sources` table (external) | `patent:US-11234567-B2` |
| `web:` | `sources` table (URL) | `web:bloomberg.com/.../article` |

Full grammar and per-scheme resolution rules live in `schemas/CITATION_GRAMMAR.md`.

## New data: the `sources` table

One new DuckDB table:

```sql
CREATE TABLE sources (
    source_uri      VARCHAR PRIMARY KEY,   -- e.g. "news:reuters/2026-04-19/intel-arm-deal"
    scheme          VARCHAR NOT NULL,      -- "news" | "transcript" | "patent" | "web"
    title           VARCHAR,
    canonical_url   VARCHAR,
    publisher       VARCHAR,
    published_at    DATE,
    accessed_at     TIMESTAMP DEFAULT now(),
    snapshot_path   VARCHAR,               -- optional local archive (HTML/PDF/text)
    notes           VARCHAR
);
```

Used **only** for citations whose source is NOT already in DuckDB. Citations to filings, prices, signal runs, etc. resolve via their own primary keys — they do **not** need a row in `sources`.

Sparse table by design: ~hundreds of rows, not millions.

## Researcher contract (drafting agent)

When the Researcher writes a claim that needs a citation, it must:

1. Pick the right scheme for the source.
2. Construct a valid URI per the grammar.
3. If the source is external (news, transcript, patent, web), **insert** a row in `sources` with metadata (title, URL, date, optionally a snapshot).
4. Embed the citation in the markdown using the format from `WIKI_UPDATE_RULES.md` Rule 3.
5. Run the Validator before producing the draft.

The Researcher cannot ship a draft with an unresolvable citation — the Validator gates this.

### `sources` table — write rules

The Researcher's permissions on `sources` are tightly scoped:

- **INSERT only.** A new external source not yet known to the system is inserted by the Researcher with full metadata.
- **UPDATE forbidden.** Once a row exists, the Researcher cannot modify it. Updates require curator approval and are logged as separate events (append-only audit history — to be defined in Phase 3).
- **DELETE forbidden.** Cited sources are immutable from the Researcher's perspective. The stability contract above (citations resolve forever) requires this.

Rationale: a Researcher rewriting a source's metadata mid-flight could silently change what every existing citation points to. Insert-only avoids that entire failure mode.

## Validator contract

For each citation key in a draft:

```python
def validate_citation(uri: str) -> Resolution:
    scheme, entity, frag = parse(uri)
    if scheme in DUCKDB_SCHEMES:
        if not exists_in_table(scheme, entity):
            return Failure(f"{uri} does not resolve in DuckDB")
    elif scheme in EXTERNAL_SCHEMES:
        if not exists_in_sources(uri):
            return Failure(f"{uri} not in sources table")
    else:
        return Failure(f"unknown scheme: {scheme}")
    return OK()
```

Pseudocode — actual implementation is Phase 3.

A draft fails the Validator if **any** citation fails to resolve. No silent drops, no "best-effort."

## Stability contract

Once a citation key is published in a live wiki page, it must continue to resolve forever. Concretely:

- **DuckDB rows that are cited must not be deleted.** Schema migrations preserve old IDs.
- **External sources are archived.** When `snapshot_path` is set, the local snapshot is the authoritative copy if the URL dies.
- **Scheme renames are forbidden.** If a new scheme is needed, a new name is added; old names continue to resolve.
- **Page renames preserve citations.** Citations point to source entities, not to wiki pages, so this is automatic — but worth stating.

## Risks and design decisions to review

1. **Source-snapshot storage cost.** Saving HTML/PDFs of every cited news article costs disk. For a personal tool this is fine (~MB scale), but the policy needs a default. Proposal: snapshot every cited external source by default; offer an opt-out for things known to be permanent (e.g., SEC EDGAR — already authoritative).

2. **`web:` scheme as escape hatch.** Last-resort scheme for URLs that don't fit a typed scheme. Risk: it becomes the default. Mitigation: `web:` citations show a warning in the daily report ("untyped source") so curator pressure pushes toward typed schemes.

3. **Composite vs. surrogate keys.** I used composite keys for `tx:`, `earnings:`, `price:`. These are stable but verbose. Alternative: an autoincrementing surrogate `event_id` per source row. Decision: stick with composite keys — they're human-readable and don't need a separate ID table.

4. **Citation density.** Open question: if a paragraph has 4 facts each needing citations, the markdown gets noisy. `WIKI_UPDATE_RULES.md` Rule 2 says "if unsure, cite," but Phase 5 (rendering) needs an opinion on inline-vs-footnote-vs-endnote presentation. Defer to Phase 5; spec doesn't constrain.

5. **The `sources` table as a write target for the Researcher.** This is the one place the Researcher writes to live DuckDB (vs. only `wiki/_drafts/`). Acceptable because the table is metadata-only and additive — but it should be auditable. Phase 3 will log every `sources` insert.

## Acceptance criteria for Phase 2 (when is the spec done?)

- `schemas/CITATION_GRAMMAR.md` exists, with a formal grammar, the schemes table, resolution rules per scheme, and ≥ 2 worked examples per scheme.
- This proposal doc exists and has been reviewed by the curator.
- The `sources` table DDL is reviewed (above).
- Risks 1–5 each have a yes/no decision recorded.
- No code has been written.

When all five are checked, Phase 2 is done and Phase 3 (implementation) can begin.

## What does NOT need to happen for Phase 2

- We don't need to ingest any news yet.
- We don't need to add the `sources` table to `db.py` yet (Phase 3).
- We don't need to update `STRATEGY.md` (it'll be reconciled when the daily-report section changes in Phase 5).
- We don't need to write any agent code.
