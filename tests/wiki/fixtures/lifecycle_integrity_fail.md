---
signal_id: volume_anomaly_5_60_t2.0
status: validated
hold_days: 30
data_sources:
  - db:prices
validated_run_id: 2
code_version: 5b6e8f1
event_max_date: 2024-12-31
lifecycle: reviewed
last_updated: 2026-05-05
last_reviewed: 2026-04-01
freshness_status: current
confidence: medium
schema_version: 1
---

# volume_anomaly (lifecycle integrity fixture)

## Definition

<!-- claim_type: factual_claim -->

Event: a `(ticker, date)` where volume spikes.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #2](signal_run:2) — 2026-05-05

- N events: 10

<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

Volume spikes indicate new information.

## Known limitations

<!-- claim_type: risk_note -->

- This is a test fixture.

## Comparable signals

<!-- claim_type: factual_claim -->

- No comparables.

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- USE when: testing the validator.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-05 — created for testing. [run_id=2](signal_run:2).
