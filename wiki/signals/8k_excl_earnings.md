---
signal_id: 8k_excl_earnings
status: borderline
hold_days: 30
data_sources:
  - db:sec_filings
  - db:prices
validated_run_id: 6
code_version: b93c6f1
event_max_date: 2024-12-30
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# 8-K Filing — Excluding Earnings (Non-Earnings Material Events)

## Definition

<!-- claim_type: factual_claim -->

Fires on 8-K filings by universe companies where the filing does not primarily report earnings results. Specifically, filings where item 2.02 (Results of Operations and Financial Condition) is the sole or primary item code are excluded. Filings that combine item 2.02 with other material items are retained.

Multiple filings by the same company on the same date are deduplicated to a single event. Entry is T+1 open.

Parameters: `exclude_earnings=True`. Data source: `db:sec_filings`, form = `8-K`.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #6](signal_run:6) — 2026-05-03

- N events: **3754** (window 2018-01-02 → 2024-12-30)
- Hit rate: **56.2%**
- Mean return: **+2.12%** over 30 trading days
- Mean alpha vs sector: **+0.46%**
- p-value vs sector: **0.0529** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.37**
- Max drawdown of sequential equity curve: **-100.0%**
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

By removing earnings-driven filings, this version isolates non-scheduled material events: new contracts, leadership changes, strategic agreements, regulatory filings, and financing events. These disclosures are harder to anticipate than earnings, so the market may react partially on the day of filing and then continue to drift as participants digest the implications over the following weeks.

Compared to [8k_any](8k_any.md), this version improves hit rate (56.2% vs 55.4%), mean return (+2.12% vs +1.95%), and Sharpe (0.37 vs 0.34) by removing the noisier earnings-coincident events. The p-value of 0.053 is just above the 0.05 bar — borderline rather than validated.

## Known limitations

<!-- claim_type: risk_note -->

- Borderline status: p=0.053, just above the 0.05 threshold. A larger sample or broader universe could resolve this either way.
- Item code filtering is imperfect. EDGAR item codes are self-reported by filers and not always consistently applied, so some earnings-adjacent filings may not be excluded.
- Excludes earnings 8-Ks by item code, but some earnings announcements are filed without item 2.02 (especially smaller companies).
- Max drawdown of -100% — the signal is diversified across events but sequential equity curve analysis shows it can string together long losing periods.

## Comparable signals

<!-- claim_type: factual_claim -->

- [8-K Filing — Any](8k_any.md) — baseline; includes earnings filings
- [8-K Item 1.01 — Material Agreement](8k_item_1_01.md) — narrower filter focused on contract-signing events

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** researching whether non-earnings disclosure events drive return drift in tech/AI names. This is the strongest of the three 8-K variants tested and warrants further investigation (broader universe, subgroup analysis by item type).
- **DO NOT use when:** the p=0.053 borderline result is treated as validated. It needs at least one confirmatory run on a broader universe or holdout period before acting on it.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=6 completed. [Results](signal_run:6). Status: borderline. p=0.053 vs sector.
