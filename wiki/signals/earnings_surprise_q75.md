---
signal_id: earnings_surprise_q75
status: graveyard
hold_days: 60
data_sources:
  - db:earnings_events
  - db:prices
validated_run_id: 4
code_version: b93c6f1
event_max_date: 2024-12-04
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: low
schema_version: 1
---

# Earnings Surprise — Top Quartile (Q75)

## Definition

<!-- claim_type: factual_claim -->

Fires when a company's reported EPS surprise falls in the top quartile of all earnings surprises observed within the iteration window (2018–2024). The surprise threshold is computed as the 75th percentile of `surprise_pct` across all events in the training window — approximately +16.7% above consensus.

Event date is BMO/AMC-adjusted: for before-market-open announcements the event date equals the announcement date; for after-market-close announcements it is shifted to the next trading day. This ensures the backtest enters at the next open after the market has had a chance to react. Data source: `db:earnings_events`, prices from `db:prices`.

Parameters: `quantile=0.75`, `hold_days=30` (run #3) and `hold_days=60` (run #4).

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #3](signal_run:3) — 2026-05-03

- N events: **410** (window 2018-01-16 → 2024-12-04)
- Hit rate: **52.0%**
- Mean return: **+1.55%** over 30 trading days
- Mean alpha vs sector: **-0.34%**
- p-value vs sector: **0.7055** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.23**
- Max drawdown of sequential equity curve: **-99.3%**

[Run #4](signal_run:4) — 2026-05-03

- N events: **410** (window 2018-01-16 → 2024-12-04)
- Hit rate: **58.0%**
- Mean return: **+4.96%** over 60 trading days
- Mean alpha vs sector: **+1.13%**
- p-value vs sector: **0.4594** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **0.31**
- Max drawdown of sequential equity curve: **-99.9%**
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

Post-earnings announcement drift (PEAD) is a well-documented anomaly: stocks with large positive earnings surprises tend to continue drifting upward for weeks after the announcement as analysts revise estimates upward and institutional investors reposition. The top-quartile filter is intended to isolate the strongest surprises where drift is most likely to persist.

However, within this universe (AI infrastructure and adjacent sectors), the sector itself may be the dominant return driver, making it harder to isolate the surprise-specific edge. The p-values of 0.46 and 0.71 indicate the alpha over the sector benchmark is indistinguishable from noise on these 410 events.

## Known limitations

<!-- claim_type: risk_note -->

- Both the 30-day and 60-day hold periods fail to show statistically significant alpha over sector. The signal is in the graveyard.
- The Q75 threshold is computed in-sample; out-of-sample (2025 holdout) behavior has not been tested.
- Universe is concentrated in high-growth tech names where earnings surprises are frequent and often already priced in via implied volatility before the announcement.
- 410 events over 7 years is a thin sample — insufficient to detect modest effects reliably.

## Comparable signals

<!-- claim_type: factual_claim -->

- [Volume Anomaly — 5/60-day](volume_anomaly_5_60_t2.0.md) — earnings announcements often produce volume spikes; some overlap with this signal is expected

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** this signal is currently graveyard status and should not be used for research conclusions without further iteration (e.g., different hold periods, sector-neutral construction, or a broader universe).
- **DO NOT use when:** drawing conclusions about PEAD in general — the failure here is specific to this universe and parameter set, not necessarily to the PEAD phenomenon.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-03 — run_id=3 completed. [Results](signal_run:3). Status: graveyard. 30-day hold, p=0.71 vs sector.
- 2026-05-03 — run_id=4 completed. [Results](signal_run:4). Status: graveyard. 60-day hold, p=0.46 vs sector.
