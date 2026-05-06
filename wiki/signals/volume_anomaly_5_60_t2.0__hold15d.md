---
signal_id: volume_anomaly_5_60_t2.0__hold15d
status: validated
hold_days: 15
data_sources:
  - db:prices
validated_run_id: 14
code_version: 8a75bd6
event_max_date: 2024-12-24
lifecycle: draft
last_updated: 2026-05-06
last_reviewed: 2026-05-06
freshness_status: current
confidence: medium
schema_version: 1
---

# Volume Anomaly ×2.0 — 15-Day Hold (Recommended)

## Definition

<!-- claim_type: factual_claim -->

Fires when a ticker's 5-day average volume exceeds 2× its 60-day median volume. Events are debounced to one firing per ticker per 5 trading days to avoid clustering on the same move. Entry is T+1 open; exit is 15 trading days after entry.

This is the **recommended operating configuration** of the volume anomaly signal, identified via hold period sweep across 5, 10, 15, 20, and 30-day holds. The 15-day hold produces the best p-value (0.0046) and near-best annualized Sharpe (0.49) across all tested periods.

Parameters: `threshold=2.0`, `window_short=5`, `window_long=60`, `debounce_days=5`, `hold_days=15`. Universe: all three sectors (ai_infra, space_defense, telecom).

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #14](signal_run:14) — 2026-05-06

- N events: **1480** (window 2018-03-28 → 2024-12-24)
- Hit rate: **54.3%**
- Mean return: **+2.17%** over 15 trading days
- Mean alpha vs sector: **+1.27%**
- p-value vs sector: **0.0046** — below the 0.05 bar — **VALIDATED**
- Sharpe (annualized): **0.49**
- Max drawdown of sequential equity curve: **-100.0%**
<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

Unusual volume is the market's loudest signal that something has changed. When 5-day average volume more than doubles the 60-day median, it suggests institutional accumulation, a significant news event, or a shift in market perception that the price has not yet fully reflected. The 15-day hold captures the period during which informed participants who acted on the catalyst continue to push price, before the move is fully arbitraged away.

The hold period sweep revealed that alpha builds steadily from day 5 to day 20 — it does not spike and reverse. This is consistent with gradual institutional accumulation rather than a retail momentum burst, and suggests the signal reflects real information rather than noise.

## Known limitations

<!-- claim_type: risk_note -->

- Max drawdown on the sequential equity curve is -100% — this signal can have catastrophic runs if events cluster in a bear market. Position sizing must account for this.
- The signal fires on all sectors equally. ai_infra volume spikes have lower sector-adjusted alpha (+0.65%) because SOXX co-moves; space_defense and telecom contribute more idiosyncratic alpha.
- Debounce of 5 days may suppress genuine re-accelerations in fast-moving names.
- 15-day hold means ~17 overlapping positions on average across the 68-ticker universe — capacity is limited for large portfolios.

## Comparable signals

<!-- claim_type: factual_claim -->

- [Volume Anomaly ×2.0 — 30d hold](volume_anomaly_5_60_t2.0__hold30d.md) — original configuration; p=0.031 but Sharpe drops to 0.35 as noise accumulates after day 20
- [Volume Anomaly ×2.0 — 10d hold](volume_anomaly_5_60_t2.0__hold10d.md) — p=0.0061, Sharpe=0.50; marginally better Sharpe but lower alpha (+1.10% vs +1.27%)
- [Volume Anomaly ×2.0 — 20d hold](volume_anomaly_5_60_t2.0__hold20d.md) — p=0.0062, highest raw alpha (+1.42%) but Sharpe begins to decline
- [Volume Anomaly ×2.0 (original)](volume_anomaly_5_60_t2.0.md) — same signal, 30d hold, the first validated version

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- **USE when:** running systematic scans for unusual accumulation across the universe; signals can be actioned T+1 open with a defined 15-day exit.
- **USE when:** looking for a validated, mechanically clean signal with no fundamental data dependency — purely price/volume based.
- **DO NOT use when:** market-wide volatility is elevated (VIX > 30) — volume spikes lose idiosyncratic meaning when the whole market is churning.
- **DO NOT use when:** a specific ticker has a known catalyst already priced in (e.g., day-before earnings) — the volume spike may be informed but the return window overlaps with a confounding event.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-06 — run_id=14 completed. [Results](signal_run:14). Status: validated.
