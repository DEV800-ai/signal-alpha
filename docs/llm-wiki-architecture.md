# LLM Wiki — Architecture (Phase 1 spec)

## Purpose

The wiki turns validated statistical signals into **decision-ready stories**.

Today the system answers: *"Has this signal historically worked?"* — a number with a p-value.
The wiki answers: *"On THIS company, given its story and history, what does this signal mean?"* — a 30-second read with sources.

The wiki is **not** a replacement for STRATEGY.md or the validation framework. It is the **narrative layer** that sits on top of validated signals.

## Where the wiki fits

```
┌────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│  RAW SOURCES       │    │  STRUCTURED FACTS    │    │  NARRATIVE LAYER   │
│  (filings, prices, │ →  │  (DuckDB)            │ →  │  (Markdown wiki)   │
│   patents, news)   │    │  prices, sec_filings,│    │  companies/...     │
│                    │    │  signal_runs, ...    │    │  sectors/...       │
└────────────────────┘    └──────────────────────┘    └────────┬───────────┘
                                                                │
                                                                ▼
                                                       ┌────────────────────┐
                                                       │  DAILY REPORT      │
                                                       │  signals + context │
                                                       └────────────────────┘
```

**Direction is one-way.** Raw → DB → Wiki → Report. The wiki never feeds back into raw data or DB facts.

## Three load-bearing rules

1. **DuckDB owns facts. Markdown owns interpretation.**
   Filings, prices, transactions, signal-run results live in DuckDB. The wiki references them by stable IDs (accession, ticker+date, run_id). The wiki never duplicates a fact that DuckDB has — it cites it.

2. **Public/investable companies are separate from private companies.**
   Different namespaces, different schemas, different rules. The wiki may cross-reference (`Stoke Space → RKLB`), but a private-company page can never be presented as an actionable position.

3. **No buy/sell recommendations.**
   The wiki and the daily report state signals and their statistics. They do not output "Suggested: buy 2%, stop 10%". The user decides. This rule overrides earlier daily-report drafts in STRATEGY.md.

## Phase scope

Each phase is split into two parts: **spec** (docs only) and **implementation** (code). No code is written until the spec for that phase is approved by the curator.

| Phase | Spec deliverable | Implementation | Status |
| --- | --- | --- | --- |
| 1 | 6 schema docs | _(none — schemas are the deliverable)_ | **Spec done** |
| 2 | `docs/llm-wiki-phase-2-spec.md` + `schemas/CITATION_GRAMMAR.md` + `schemas/VALIDATOR_RULES.md` | `sources` table DDL applied; Validator skeleton | **Spec in review** |
| 3 | proposal doc | Researcher pipeline + draft → live workflow + audit log | Deferred |
| 4 | proposal doc | Per-company "watchlist score" — aggregated signal firings (NOT a rebrand of backtest validation) | Deferred |
| 5 | proposal doc | Context-pack generation; daily report rendering | Deferred |
| 6 | proposal doc | Dashboard integration | Deferred |

**Rule:** every phase ends with curator approval of its spec docs. Implementation begins only after sign-off.

## File layout (proposed for Phase 2+)

```
schemas/                         # rules — checked into git, versioned
  COMPANY_SCHEMA.md
  SECTOR_SCHEMA.md
  SIGNAL_SCHEMA.md
  WIKI_UPDATE_RULES.md
  AGENTS.md

wiki/                            # the wiki itself — written by humans + agents
  companies/
    public/
      INTC.md                    # one page per investable ticker
      NVDA.md
      ...
    private/
      stoke-space.md             # private companies — separate namespace
  sectors/
    ai_infra.md
    space_defense.md
    telecom.md
  signals/
    volume_anomaly.md            # one page per validated signal
    ...
```

Phase 1 creates only the `schemas/` files. The `wiki/` tree is created in Phase 3.

## What this proposal explicitly does NOT do

- Does not edit any existing code (`backtest.py`, `db.py`, signal modules).
- Does not add new DuckDB tables.
- Does not introduce LLM calls.
- Does not add a UI or dashboard.
- Does not modify STRATEGY.md (a separate review will reconcile any conflicts).
- Does not start ingesting private-company data.

## How wiki integration changes the existing daily-report draft

STRATEGY.md Phase 6 currently shows:

```
INTC — 8-K Item 1.01 (material agreement)
  Suggested: 2% position, 30-day hold, 10% stop      ← this line is dropped
```

Under the wiki rules, the daily report becomes:

```
INTC — 8-K Item 1.01 (material agreement)
  Stats (2018–2024): N=312, mean 30d +1.8%, vs SOXX +0.4%, p=0.02
  Context: companies/public/INTC.md (last reviewed 2026-04-22)
```

The "suggested action" line is removed. STRATEGY.md will be updated separately when Phase 5 (context-pack generation) lands.

## Rendering example — citations in source vs. final output

Markdown source (lives on disk, written by Researcher / curator):

```markdown
The deal was announced via 8-K [Item 1.01 dated 2026-04-22](filing:0001127602-26-018000#item-1.01)
and discussed on the [Q1 2026 call (p.4)](transcript:INTC:2026-Q1#p4).
The volume_anomaly signal has [validated alpha of +1.37% vs sector](signal_run:2)
on a 30-day hold.
```

Daily report rendering (Phase 5 — what the user actually sees):

```
INTC — 8-K Item 1.01 (material agreement)
  Stats (2018–2024): N=312, mean 30d +1.8%, vs SOXX +0.4%, p=0.02
  
  CONTEXT (companies/public/INTC.md, last reviewed 2026-04-22, confidence: medium)
    The deal was announced via 8-K Item 1.01 dated 2026-04-22 [1] and
    discussed on the Q1 2026 call (p.4) [2]. The volume_anomaly signal
    has validated alpha of +1.37% vs sector [3] on a 30-day hold.
  
  Sources:
    [1] filing:0001127602-26-018000  → SEC EDGAR / accession 0001127602-26-018000
    [2] transcript:INTC:2026-Q1      → sources table / cached snapshot
    [3] signal_run:2                 → DuckDB signal_runs row
```

Three things to notice:

1. The `[N]` reference numbers are added at render time. The wiki source uses URI citations — the renderer assigns numbers per page.
2. Each source line shows the resolution target — DuckDB row, SEC URL, sources-table snapshot — so the user can follow the chain.
3. The page-level `confidence` field is shown alongside `last_reviewed`. A low-confidence page renders with a smaller / muted context block.

Stale page rendering (when `last_reviewed > 90 days` or `freshness_status: stale`):

```
  CONTEXT (companies/public/INTC.md — STALE, last reviewed 2025-08-12)
    [context block omitted — see signal_runs row for raw stats]
```

The Reporter agent (Phase 5) skips the context body for stale pages and shows only a flag. The user can still navigate to the page manually.

## The decision surface — Context Pack

The three layers (DuckDB → Validator → Wiki) need a single output that the user actually consumes when a signal fires. That output is a **Context Pack**.

A Context Pack for a single signal firing is the bundle of:

```
Context Pack
├── signal stats          (signal_runs row — alpha, p-value, N, hit rate, sample period)
├── company page          (companies/public/<TICKER>.md — bull/bear/priced-in/watch)
├── sector page slice     (sectors/<sector_id>.md — active themes, recent catalysts)
├── recent events         (latest filings/earnings/transactions for this ticker)
└── meta                  (lifecycle, confidence, freshness — so the user sees trust state)
```

This is the unit the daily report assembles per firing, and it is the unit the curator can copy into notes / PRs / messages.

**Why it matters:**
- Without a defined Context Pack, the wiki and the signal stats live in separate silos and the user re-stitches them every time.
- With it, the Reporter agent has one job: assemble Context Packs, render them, write the daily report.

**Phase mapping:**
- **Phase 5** — Context Pack assembly + rendering. A separate spec doc lives at `docs/llm-wiki-phase-5-spec.md` (deferred). This section is just the placeholder.
- The schemas in Phase 1 already constrain enough structure (frontmatter, sections, citations) that Phase 5 has a deterministic input.

Treat this section as a **promise**, not a specification — the full schema for a Context Pack lands when Phase 5 begins.

## Cost / effort honesty

Phase 1 (this work): ~zero ongoing cost. Schemas are static.

Phase 2–5 will introduce:
- LLM tokens for page drafting (capped — pages updated only on material new info, not daily)
- Curator time for review (this is the real cost)

A wiki built and abandoned is worse than no wiki — stale narrative misleads more than missing narrative. The schemas in Phase 1 must include staleness rules so dead pages flag themselves.
