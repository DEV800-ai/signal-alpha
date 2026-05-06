---
signal_id: 8k_item_1_01
status: graveyard
hold_days: 30
data_sources:
  - db:sec_filings
  - db:prices
validated_run_id: 7
code_version: b93c6f1
event_max_date: 2024-12-27
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: low
schema_version: 1
---

# 8-K Item 1.01 — Entry into Material Definitive Agreement

## Definition

<!-- claim_type: factual_claim -->

Fires on 8-K filings that contain item code 1.01 — "Entry into a Material Definitive Agreement." Under SEC rules, companies must file an 8-K within four business days of entering into a material contract, amendment, or other agreement that is not in the ordinary course of business.

Filings are filtered to those where the `items` field contains `1.01`. Multiple filings by the same company on the same day are deduplicated. Entry is T+1 open.

Parameters: `item_filter="1.01"`, `hold_days=30`. Data source: `db:sec_filings`.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #7](signal_run:7) — 2026-05-03

- N events: **592** (window 2018-01-04 → 2024-12-27)
- Hit rate: **54.6%**
- Mean return: **+1.63%** over 30 trading days
- Mean alpha vs sector: **+0.50%**
- p-value vs sector: **0.3685** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.28**
- Max drawdown of sequential equity curve: **-99.8%**
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

Material definitive agreements — licensing deals, supply contracts, joint ventures, partnership agreements — represent strategic inflection points that may take time for the market to fully price in. Unlike earnings, which are widely anticipated, a new partnership agreement disclosed in an 8-K may receive limited analyst coverage initially, leaving room for subsequent drift as the strategic implications become clearer.

However, "material" is self-assessed by the filer, and item 1.01 covers a wide range of agreements from transformative partnerships to routine renewals. The p=0.37 result suggests that at this level of aggregation, the signal does not produce meaningful alpha over sector — the agreements are too heterogeneous.

## Known limitations

<!-- claim_type: risk_note -->

- Graveyard status: p=0.37 vs sector, not significant.
- Item 1.01 aggregates highly heterogeneous events (transformative deals alongside routine contract renewals). Subgroup analysis by deal type or counterparty could reveal a narrower edge.
- 592 events is a relatively thin sample for detecting modest effects. A broader universe would help.
- Some item 1.01 filings are combinatory — filed alongside other items — which may dilute the clean signal of a standalone agreement announcement.

## Comparable signals

<!-- claim_type: factual_claim -->

- [8-K Filing — Excluding Earnings](8k_excl_earnings.md) — broader set of non-earnings filings; stronger edge despite lower specificity
- [8-K Filing — Any](8k_any.md) — baseline, all 8-K events

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** investigating whether a specific type of agreement (e.g., AI infrastructure contracts, government awards) has predictive power. The aggregate signal fails, but a sub-filtered version targeting high-value agreements may succeed.
- **DO NOT use when:** looking for a ready-to-use signal. This is graveyard status and requires further iteration before drawing conclusions.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=7 completed. [Results](signal_run:7). Status: graveyard. p=0.37 vs sector.
