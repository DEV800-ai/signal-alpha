# Sector page schema

Applies to: every page under `wiki/sectors/`.

A sector page is the bridge between (a) cross-cutting themes that move several companies at once, and (b) the individual company pages. It is shorter than a company page — it does not duplicate per-company analysis.

## Frontmatter

```yaml
---
sector_id: ai_infra                       # must match `sector` values in COMPANY_SCHEMA frontmatter
name: AI Infrastructure
benchmark_etf: SOXX                       # primary benchmark used in backtests for this sector
secondary_etf: IGV                        # optional second benchmark
lifecycle: validated                      # draft | validated | reviewed
last_updated: 2026-05-04                  # auto — set by Validator on body changes
last_reviewed: 2026-04-22                 # CURATOR-ONLY
freshness_status: current                 # current | stale | needs_review
confidence: medium                        # low | medium | high
schema_version: 1
---
```

Validation:
- `sector_id` must match an entry in `data/universe.csv` `sector` column.
- `benchmark_etf` must match a benchmark in `data/universe.csv` (`sector = 'benchmark'`).

## Required sections

Each section has a default `claim_type` (see `schemas/VALIDATOR_RULES.md`).

### 1. Sector thesis (≤ 100 words)
**Default claim_type:** `interpretation`

The single-paragraph version of why this sector matters and what's driving it now. Avoid timeless statements; bias toward "as of 2026, the dominant story is X."

### 2. Active themes (≤ 5)
**Default claim_type:** `interpretation` — each theme typically *embeds* `factual_claim` citations

Themes are forces that affect multiple companies. Each gets one short bullet + the companies most exposed.

```
- AI capex super-cycle: hyperscalers spending $250B+ collectively in 2026.
  Most exposed: NVDA, AVGO, AMD, TSM, ANET. [Sources: hyperscaler 10Qs, ARK reports]
```

A theme listed here implies the company pages of the named tickers should reference it.

### 3. Constituents (table) — auto-generated
**Default claim_type:** `factual_claim`

| Ticker | Status | Wiki page | Role in sector |
| --- | --- | --- | --- |
| NVDA | active | [NVDA](../companies/public/NVDA.md) | Compute (training) |
| AVGO | active | [AVGO](../companies/public/AVGO.md) | Networking + custom ASIC |

Generated, not hand-curated. Phase 4 wires this to `data/universe.csv`. Wrapped in `<!-- AUTOGEN:BEGIN constituents --> ... <!-- AUTOGEN:END constituents -->` markers per `AGENTS.md`.

### 4. Cross-sector dependencies
**Default claim_type:** `interpretation`

Themes from this sector that ripple into others.

```
- AI capex → telecom equipment demand (5G core upgrades for AI traffic)
  Affects telecom sector page; cross-link.
```

### 5. Sector-level catalysts (rolling 12 months)
**Default claim_type:** `factual_claim` — every row MUST cite

Events that affected the sector ETF itself or > 50% of constituents on the same day.

| Date | Event | Sector ETF return (5d) | Source |
| --- | --- | --- | --- |
| 2025-01-27 | DeepSeek model release sparks compute-cost re-rating | SOXX -8% | [news/2025-01-27/Reuters](news:reuters/2025-01-27/deepseek) |

### 6. Open questions
**Default claim_type:** `interpretation`

Things the sector page does NOT have a strong answer for, by design. Naming them prevents false certainty.

```
- Does AI capex peak in 2027 or run through 2030? Hyperscaler guidance gives both.
- Is custom ASIC adoption (TPU, MTIA, MAIA) net negative for NVDA share, or just additive?
```

## Anti-patterns

- **Restating company pages.** Sector pages are about the sector, not biographies of constituents.
- **Forecasts disguised as themes.** "GPU shortage will end in 2027" is a forecast. "Lead times shortening from 52 to 36 weeks per AVGO Q4 call" is a theme bullet.
- **Generic platitudes.** "AI is transformative" — delete and rewrite with substance.

## Edit rules

- Sections 3 (constituents) and parts of 5 (catalyst returns) auto-generate; do not hand-edit. Auto-generated regions are bracketed by `<!-- AUTOGEN:BEGIN/END -->` markers per `AGENTS.md`.
- All other sections are human/agent-editable with citations.
- `last_updated` is auto-bumped by the Validator on any body change. `last_reviewed` is **curator-only** (see `WIKI_UPDATE_RULES.md` Rule 8).
- Sector pages reviewed at least quarterly even if no obvious change — sector narratives drift faster than company narratives.
