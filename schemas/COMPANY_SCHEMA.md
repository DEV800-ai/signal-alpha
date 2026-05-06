# Company page schema

Applies to: every page under `wiki/companies/public/` and `wiki/companies/private/`.

## Frontmatter (required)

```yaml
---
ticker: INTC                          # public: NYSE/NASDAQ symbol. private: omit and use slug instead
slug: intc                            # filename stem; lowercase, kebab-case
name: Intel Corporation
status: public                        # one of: public | private | delisted
sector: ai_infra                      # must match a sector_id in schemas/SECTOR_SCHEMA.md
listing: NASDAQ                       # public only
public_proxy: null                    # private only — ticker(s) that give exposure (e.g., RKLB)
lifecycle: validated                  # draft | validated | reviewed — see VALIDATOR_RULES.md
last_updated: 2026-05-04              # auto — set to today by Validator on any body change
last_reviewed: 2026-04-22             # CURATOR-ONLY — Validator never modifies this
freshness_status: current             # current | stale | needs_review (defaults derived from last_reviewed)
confidence: medium                    # low | medium | high — curator's read on how well-sourced this page is
schema_version: 1
---
```

Validation rules:

- `status: public` requires `ticker` to exist in `data/universe.csv`.
- `status: private` requires `ticker` to be absent and `public_proxy` to be present (can be `[]` if no proxy).
- `lifecycle`: workflow stage — `draft` (in `_drafts/`, not live) → `validated` (passed Validator) → `reviewed` (curator approved). Body changes demote the page to `draft` until re-validated.
- `last_updated`: ISO date, auto-managed. Validator FAILS the page if body content changed but `last_updated` is not today.
- `last_reviewed`: **curator-only.** Validator never writes this. May WARN if `last_updated - last_reviewed > 90 days`.
- `freshness_status`: defaults to `current`. Auto-derived from `last_reviewed`: pages > 90 days behind become `stale`. Curator may override to `needs_review` for explicit attention requests.
- `confidence`: curator-set. Defaults below. Daily report rendering treats `low`-confidence pages with a smaller / muted context block.

**Default confidence by lifecycle state:**

| State | Default `confidence` | Rationale |
| --- | --- | --- |
| `lifecycle: draft` | `low` | not yet validated |
| `lifecycle: validated`, never curator-reviewed | `low` | structure passed; analysis unverified |
| `lifecycle: validated`, `last_reviewed` within 30 days | `medium` | curator has read it recently |
| `lifecycle: reviewed` | no default — curator chooses explicitly | `high` requires a reason logged in the next page edit |

Company pages don't get a `high` baseline on validation alone — unlike signal pages, structural validation doesn't tell you whether the *analysis* is good. Drift from this table is allowed; it logs an entry in §7 watch list with the reason.

## Required sections (in this order)

Each section has a default `claim_type` (see `schemas/VALIDATOR_RULES.md` for what this means for citation enforcement). Override the default inline only when a section mixes types.

### 1. Strategic position (≤ 80 words)
**Default claim_type:** `interpretation`

What the company actually does and where it fits in its sector. Avoid promotional language. Avoid future-tense claims without sources.

### 2. Bull case (≤ 3 bullets)
**Default claim_type:** `interpretation` (each bullet typically *contains* a `factual_claim` citation)

Each bullet: one-sentence claim + inline source citation. No price targets.

```
- Foundry capacity ramps to 18A node by Q4 2026, enabling external customers like MSFT [10K-2026-FY/p.34](filing:0000050863-26-000045#p34).
```

### 3. Bear case (≤ 3 bullets)
**Default claim_type:** `risk_note`

Symmetric to bull case. Required even if you think the company is great.

### 4. What is priced in (≤ 60 words)
**Default claim_type:** `interpretation`

The narrative reflected in current consensus. Sourced when possible (analyst notes), narrative-style when not. The point: separate "new information" from "already-known story" when a signal fires.

### 5. Recent catalysts (table, last 12 months)
**Default claim_type:** `factual_claim` — every row MUST cite a source

| Date | Event | Source | Horizon | Outcome |
| --- | --- | --- | --- | --- |
| 2024-09-13 | ARM design partnership announced | [8-K Item 1.01](filing:1234567#item-1.01) | 30d | +6% |

Column rules:
- **Source** — required citation; the URI goes in the link target, not the human-readable label. Bad: `[filing:1234567](filing:1234567)`. Good: `[8-K Item 1.01](filing:1234567#item-1.01)`.
- **Horizon** — required; one of `5d` / `30d` / `60d` / `90d`. The horizon used to compute Outcome.
- **Outcome** — populated only after the horizon window completes. Never predicted. Empty cell is allowed for events whose horizon hasn't elapsed.

### 6. Signal history (auto-generated, do not edit by hand)
**Default claim_type:** `signal_summary` — every row cites `signal_run:N`

A read of `signal_runs` filtered to this ticker, showing prior signal firings and their realized outcomes. Phase 4 generates this section; humans only edit sections 1–5 and 7. Wrapped in `<!-- AUTOGEN:BEGIN signal_history --> ... <!-- AUTOGEN:END signal_history -->` markers per `AGENTS.md`.

### 7. Watch list
**Default claim_type:** `risk_note`

Concrete things to watch. Each entry has a measurable trigger.

```
- Q3 earnings: foundry-segment gross margin > -10%
- Any 8-K Item 1.01 mentioning external foundry customer
- USPTO grants on advanced packaging > 5/quarter
```

## Anti-patterns (do not write these)

- **Price targets.** "$60 by year-end." Out of scope and tonally wrong.
- **Buy/sell language.** "Looks like a buy here." Replaced by signal stats.
- **Unsourced opinion.** "Insiders are clearly accumulating." Cite Form 4 filings or omit.
- **Stale claims dressed as current.** Always date-stamp claims that decay.
- **Restating DuckDB facts.** "Intel filed 312 8-Ks since 2018" — derive that from the DB, don't transcribe it.

## Public vs. private differences

| Aspect | Public page | Private page |
| --- | --- | --- |
| Frontmatter `ticker` | required | absent |
| Frontmatter `public_proxy` | absent | required (can be empty list) |
| Section 6 (signal history) | populated from `signal_runs` | always empty |
| Daily report eligibility | yes | NO — private companies are never in the daily report's actionable list |
| Cross-link from public | yes (e.g., RKLB → Stoke Space) | yes (e.g., Stoke Space → RKLB) |
| Default claim_type | per-section as above | every section escalates one level: `private_company_context` is the strictest tier and applies to factual claims about a private company. No SEC filings = higher citation bar (news, press releases, primary sources). |

## Worked example (public)

See **future** `wiki/companies/public/INTC.md` (created in Phase 3). For Phase 1 spec purposes, the structure above is binding.

## Edit rules

- Humans and named agents can edit sections 1–5 and 7.
- Section 6 is regenerated only — never hand-edited.
- `last_updated` is auto-bumped by the Validator on any body change. `last_reviewed` is **curator-only** — set when the curator reads the page and confirms it still reflects reality (see `WIKI_UPDATE_RULES.md` Rule 8).
- Any claim added to bull/bear/priced-in MUST cite a source from DuckDB or an external link with a date.
