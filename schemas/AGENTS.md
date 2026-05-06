# Agents

The agent vocabulary is fixed in this spec so future automation has a clear place to land. The **implementations** are introduced phase-by-phase — most roles are specifications today, not running processes.

Goal: agentic architecture, minimum implementation cost. Each role is a slot. Slots fill as phases ship.

## Implementation status

| Role | Today (Phase 1) | Phase 2–3 | Phase 4+ |
| --- | --- | --- | --- |
| **Curator** | you, manually | same | same |
| **Researcher** | spec only | a single Claude Code subagent that drafts page updates on trigger | could split per-sector or per-signal-type |
| **Validator** | spec only | a function the Researcher calls before producing a draft | could become a separate quality-bar agent |
| **Reporter** | spec only | a Python script (not really an agent) | could become an agent that adapts report shape |
| **Auto-generator** | spec only | a Python script — stays a script by design (deterministic) | unchanged |

Phase 1 ships **none of these as running code**. The doc reserves the names so Phase 2+ work has a clean place to attach.

## Roles

### Curator (you)

The only role that commits live wiki pages. All agent output flows through curator review.

Responsibilities:
- Review Researcher drafts (in `wiki/_drafts/...`) and either edit + merge into `wiki/companies/...` etc., or reject.
- Decide signal status transitions (validated / borderline / graveyard / deprecated).
- Adjudicate source conflicts when an agent flags one.

The curator is **not** expected to write pages from scratch. The expectation is review-and-adjust.

### Researcher

Reads sources, drafts wiki page updates. **Never writes to live wiki paths** — only to `wiki/_drafts/`.

Reads:
- DuckDB tables (read-only)
- Filing texts via SEC EDGAR
- News (when wired up — Phase 2+)
- Existing wiki pages (for context, not modification)

Writes:
- Drafts in `wiki/_drafts/<page-path>.md` (or as configured in Phase 3)

Constraints (enforced by Validator before draft is produced):
- Every claim has a citation key (Rule 2 of WIKI_UPDATE_RULES) — **hard FAIL** if missing
- Cannot modify auto-generated sections — **hard FAIL** if violated
- Schema budgets (≤ 80 words, ≤ 3 bullets, etc.) — **soft (SHOULD respect)**: Researcher targets the budget, Validator only WARNs if exceeded. Budgets are a discipline guideline, not a contract.

Triggers (Phase 3+ design):
- New filing for a watched ticker (8-K, 10-Q, 10-K, Form 4)
- Stale page reaching `last_reviewed > 90 days`
- Curator-initiated request ("update INTC bull/bear given Q1 2026 transcript")

The agent does not run continuously — it runs on triggers and produces a finite draft.

### Validator

Mechanical checks invoked by the Researcher before a draft is finalized. **No interpretive judgment.**

Checks:
- Frontmatter schema compliance (required fields, valid sector_id, namespace)
- Citation keys resolve to real DuckDB rows / external IDs
- Section lengths within budget
- Public/private namespace correctness
- `last_reviewed` updated

Output: PASS, or a list of failures the Researcher must fix. A draft with Validator failures is never written to disk.

In Phase 2–3, Validator is a function called inside the Researcher pipeline. It may become a separate process later if multiple sources of drafts emerge.

### Reporter

Read-only. Composes the daily report from validated signals + the wiki state.

Reads:
- `signal_runs` (DuckDB) for today's firings
- Live company pages for context blocks
- Sector pages for cross-cutting themes

Writes:
- Daily report to `reports/YYYY-MM-DD.md`

Constraints:
- Never modifies the wiki
- Skips stale pages (Rule 6) and replaces their context block with a "stale — verify" flag
- Never includes private-company pages in the actionable list

In Phase 5 this is implemented as a Python script. The agent name is reserved if a future LLM-based reporter is needed.

### Auto-generator

Deterministic process — explicitly **not** an LLM agent. Listed here because it does write to wiki files, on the narrow auto-generated sections.

Generates:
- Signal page Section 2 (validation summary) from `signal_runs` — marker name `validation_summary`
- Company page Section 6 (signal history) from `signal_runs` — marker name `signal_history`
- Sector page Section 3 (constituents) from `data/universe.csv` — marker name `constituents`
- Sector page Section 5 (catalyst return rows) from prices — marker name `catalyst_returns`

**Hard rules — auto-generator scope (load-bearing):**

- **Only writes between explicit markers.** Each auto-generated section is wrapped:
  ```
  <!-- AUTOGEN:BEGIN signal_history -->
  ...content...
  <!-- AUTOGEN:END signal_history -->
  ```
  The auto-generator overwrites only the content between matching markers.
- **Never touches frontmatter.** No frontmatter field — including `last_updated`, `last_reviewed`, `lifecycle` — is ever written by the auto-generator.
- **Never touches non-marked content.** If a marker pair is missing on a page that should have it, the auto-generator FAILs (loud) and writes nothing — it does not invent a section position.
- **Idempotent** — repeated runs produce byte-identical output.
- **Failures are loud** — no silent partial writes; either the section is fully replaced or the page is left untouched and an error is reported.

## Permissions matrix

| | Read DuckDB | Read raw filings | Read wiki | Write `_drafts/` | Write live wiki | Write daily report | `sources` table |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Curator | yes | yes | yes | yes | **yes** | yes | INSERT / UPDATE / DELETE |
| Researcher | yes | yes | yes | yes | no | no | **INSERT only** |
| Validator | yes | no | drafts only | no | no | no | read-only |
| Reporter | yes | no | yes | no | no | yes | read-only |
| Auto-generator | yes | no | yes | no | yes (auto sections only) | no | none |

`sources` table notes:
- Researcher inserts new external sources (news / transcript / patent / web).
- Researcher cannot modify existing rows. UPDATE requires curator approval (Phase 3 audit log records every update with a reason).
- DELETE is curator-only and discouraged — citations must remain resolvable.

## Workflow (simple version)

```
trigger → Researcher reads sources → drafts page → Validator inside Researcher → wiki/_drafts/<page>.md
                                                                                   │
                                                                                   ▼
                                                                            you read the diff,
                                                                            edit if needed,
                                                                            git mv → wiki/<page>.md
                                                                            (or delete the draft)
```

There is no formal approval ceremony. The "approval" is `git mv` (or copy-paste-and-edit). The audit trail is git history.

**Concurrency rule — one active draft per page:**

- A page (e.g., `wiki/companies/public/INTC.md`) can have at most one active draft (e.g., `wiki/_drafts/companies/public/INTC.md`) at a time.
- If a new trigger fires while an active draft exists, the trigger is **skipped** (Researcher logs the skip with the trigger id) until the curator clears the draft (`git mv` to live, or delete).
- "Merge two drafts" is **not supported in v1.** If the curator wants the second trigger's content, they discard the first draft first.
- Locking is filesystem-based: the existence of `wiki/_drafts/<path>.md` is the lock. No separate lock store.

This avoids race conditions in v1 without introducing concurrency primitives.

## Audit

Every wiki edit produces a git commit with a structured message:

```
[wiki] update companies/public/INTC.md

Source: researcher_agent_v1
Trigger: new 8-K filed 2026-04-22 (accession 1234567)
Sections changed: bull case (bullet 2), recent catalysts table
Citations added: filing:1234567, transcript:INTC:2026-Q1#p4
Approved by: curator (manual edit + commit)
```

For Phase 1, this format is aspirational. Phase 3 wires it up.

## Hard rules

1. The curator is the **only** writer to live wiki paths (with the narrow exception of the auto-generator on its designated sections).
2. No agent calls a paid data source without explicit curator configuration.
3. No agent runs without a logged trigger (new filing, stale page, manual invocation).
4. If a citation cannot be resolved, the draft fails the Validator — it does not ship an unsourced claim.

## Open questions (deferred)

These do not block Phase 1 but need answers before Phase 3 implementation:

- Agent invocation model — Claude Code subagent? Cron? Filesystem watch?
- Trigger plumbing — where does "new filing detected" come from? Probably an extension of `signalalpha.edgar`.
- Multiple drafts on the same page — pick latest, or refuse?
- Throttling — how many auto-triggered agent runs per day before the curator drowns in drafts?
