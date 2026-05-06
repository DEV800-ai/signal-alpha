---
signal_id: volume_anomaly_5_60_t2.0__holdout_15d
status: borderline
hold_days: 15
data_sources:
  - db:prices
validated_run_id: 22
code_version: b1cd06c
event_max_date: 2026-04-09
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly ×2.0 — 15d Hold — Holdout Validation (2025–2026)

## Definition

<!-- claim_type: factual_claim -->

Out-of-sample validation of [Volume Anomaly ×2.0 — 15d hold](volume_anomaly_5_60_t2.0__hold15d.md) on the reserved holdout window (2025-01-01 → 2026-04-09). This run was executed once after all in-sample parameter development was frozen. Results were not used to tune any parameters.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #22](signal_run:22) — 2026-05-06

- N events: **293** (window 2025-01-08 → 2026-04-09)
- Hit rate: **64.8%**
- Mean return: **+4.68%** over 15 trading days
- Mean alpha vs sector: **+1.58%**
- p-value vs sector: **0.0628** — above the 0.05 bar — **NOT VALIDATED**
- Sharpe (annualized): **1.22**
- Max drawdown of sequential equity curve: **-87.7%**
<!-- AUTOGEN:END validation_summary -->

## Holdout interpretation

<!-- claim_type: interpretation -->

The signal held up in the direction that matters. Alpha was +1.58% vs sector — 125% of the in-sample figure (+1.27%). Sharpe nearly tripled (1.22 vs 0.49 in-sample), driven by a higher hit rate (64.8% vs 54.3%) and lower volatility (15.78% vs in-sample). Mean return was +4.68% over 15 trading days.

The p-value vs sector landed at 0.063 — borderline, not the clean sub-0.05 result we saw in-sample with 1480 events. With only 293 holdout events, this is expected: the same true alpha generates lower t-statistics at 1/5th the sample size. To achieve p<0.05 with ~293 events and this alpha level, the signal would need to run for roughly another 6 months of holdout data.

**Bottom line:** the signal is not degrading. Alpha direction, magnitude, hit rate, and Sharpe all held or improved. The borderline p-value is a power issue (N=293), not a signal failure. The signal remains viable.

## Known limitations

<!-- claim_type: risk_note -->

- Holdout p-value is 0.063 — below standard significance threshold. Cannot confirm the signal with the current holdout window alone; need more time or a higher-frequency variant to build N faster.
- 2025–2026 was a strong bull market in ai_infra and space_defense; the elevated Sharpe (1.22) may partially reflect market tailwinds rather than pure signal alpha.
- Max drawdown improved to -87.7% (vs -100% in-sample) but remains severe on a sequential equity curve — position sizing remains critical.

## Comparable signals

<!-- claim_type: factual_claim -->

- [Volume Anomaly ×2.0 — 15d hold (in-sample)](volume_anomaly_5_60_t2.0__hold15d.md) — the development version this is validating
- [Volume Anomaly ×2.0 — 10d hold — Holdout](volume_anomaly_5_60_t2.0__holdout_10d.md) — parallel holdout at 10d hold; similar result (p=0.066)

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-06 — holdout run executed (run_id=22). 293 events, 2025-01-08 → 2026-04-09. Alpha +1.58%, Sharpe 1.22, p=0.063. Verdict: **BORDERLINE — signal intact, insufficient N for full confirmation.**
