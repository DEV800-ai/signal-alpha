# Wiki update rules

These rules are mandatory. They prevent the wiki from becoming a second source of truth that drifts from reality.

Mechanical enforcement of these rules lives in `schemas/VALIDATOR_RULES.md`. Anything stated here that the Validator cannot enforce is a curator-discretion rule.

## Rule 1 — DuckDB owns facts. Markdown owns interpretation.

If a fact lives in DuckDB (price, filing, transaction, signal_run), the wiki **cites it**, never **transcribes it**. A wiki page that says "Intel filed 312 8-Ks since 2018" is wrong by construction — that number must be derived from `sec_filings` at render time.

A page that says "Intel's most material 8-K in 2024 was the ARM design partnership announcement" is fine — that's interpretation, not fact transcription.

## Rule 2 — Every claim that isn't obvious narrative needs a source

Claims requiring citations:
- Specific numbers (revenue, capex, share count, prices)
- Dated events ("filed an 8-K on", "announced on")
- Quotes or paraphrases of management/analysts
- Comparisons to consensus or to other companies

Claims NOT requiring citations:
- One-line definitions of common terms ("hyperscaler = AWS/Azure/GCP/Meta/Oracle")
- Sector-of-business statements ("Intel makes CPUs and now operates a foundry")
- Pure interpretive bridge sentences

If unsure, cite. Cheaper than retracting.

## Rule 3 — Citation format

Inline link with a stable ID. The renderer (Phase 5) resolves these to URLs.

```
[8K-1234567/Item 1.01](filing:1234567)
[Q1 2026 transcript p.4](transcript:INTC:2026-Q1#p4)
[news/Reuters/2026-04-19](news:reuters/2026-04-19/intel-arm-deal)
[run_id=2](signal_run:2)
```

Citation keys map to DuckDB rows or external sources. Phase 2 defines the exact ID grammar.

## Rule 4 — No buy/sell recommendations

The wiki and the daily report state signals and their statistics. They never say:

- "Buy / sell / hold X"
- "Suggested position: 2%, stop 10%"
- "Looks attractive at these levels"

This rule **overrides** earlier daily-report drafts in `STRATEGY.md` Phase 6. The user makes the trade decision; the system surfaces information.

The closest the wiki may go: "Signal X fired today; signal X has historically averaged Y% with p=Z over 30d on this sector." That is a description of past behavior, not a recommendation.

## Rule 5 — Public/private separation is enforced by namespace

```
wiki/companies/public/INTC.md     ← can be referenced from daily report
wiki/companies/private/stoke-space.md   ← cannot be referenced from daily report
```

Cross-links allowed in both directions in narrative sections, but the rendering pipeline never lifts a private company into "actionable" output. A private company's `public_proxy` field is the only bridge.

## Rule 6 — Staleness

Every page has `last_reviewed`. Pages with `last_reviewed > 90 days` ago are flagged in the daily report as "stale context — verify before relying."

A stale page is never deleted automatically. It is flagged for human review.

A page declared `stale_irrelevant: true` in frontmatter is exempt from staleness alerts but stops being included in daily-report context.

## Rule 7 — Conflict resolution

When two sources disagree:

- **Both** are cited.
- The narrative explicitly notes the conflict.
- The page does NOT silently pick one source as truth.

```
The CHIPS Act funding milestone is reported as $7.86B by Reuters [news/.../1]
and $8.5B by Bloomberg [news/.../2]. The discrepancy is attributable to
loan vs. grant accounting (see Phase 2 of the funding agreement).
```

## Rule 8 — Edits

| Editor | Sections allowed | Writes to |
| --- | --- | --- |
| Curator (you) | All sections | `wiki/...` (live) |
| Researcher agent | Sections 1–5 and 7 of company / sector / signal pages | `wiki/_drafts/...` (only) |
| Validator | (no edits — gates Researcher output) | — |
| Reporter | (no edits — read-only) | `reports/YYYY-MM-DD.md` |
| Auto-generator | Auto-generated sections only (Section 6 of company pages; Section 3 of sector pages) | `wiki/...` (live, narrow) |

**Date-field discipline:**

- All edits update `last_updated` — auto-managed (Validator FAILs the page if body changed but `last_updated` is not today).
- **Only the curator updates `last_reviewed`.** No agent, no script, no auto-process touches this field.

This split means an agent can mechanically re-draft a page (bumping `last_updated`) without falsely claiming the curator has re-reviewed it.

Agent drafts land in `wiki/_drafts/<path>.md`. Promotion to live is a curator action — typically `git mv`, copy-paste-and-edit, or rejection by deleting the draft. There is no formal approval ceremony; git history is the audit log (see `AGENTS.md` "Audit").

## Rule 9 — No predictions

Statements about the future are allowed only when:
- They cite a public guidance source ("Intel guides foundry breakeven by 2027 [Q1 2026 transcript p.3]")
- They are framed as conditional ("If foundry margin reaches -5% by Q4, that would mark...")

Plain forecasts written in the wiki's voice ("foundry will break even in 2027") are forbidden.

## Rule 10 — Anti-patterns

- **The wiki as note-dump.** Every section earns its place. Empty subsections are removed.
- **The wiki as PR for a position.** Bull case must be balanced by bear case. If one is empty, neither ships.
- **Restating training data.** "NVIDIA was founded in 1993..." — we don't need this.
- **Aggregator-style claims.** "Many analysts believe..." with no citation. Cite or delete.
- **Page sprawl.** Each page has a length budget per section in COMPANY/SECTOR/SIGNAL schemas. Hitting the budget is a feature, not a bug.

## Rule 11 — Decision logs are append-only

Section 7 of company pages and signal pages is a chronological log. Edits to past entries require a strikethrough, never a silent rewrite.

```
- 2026-04-22 — Updated bull case: ~~ARM partnership Q4 2026~~ ARM partnership delayed to Q1 2027 per [Q1 2026 transcript].
```
