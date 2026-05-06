# Signal page schema

Applies to: every page under `wiki/signals/`. One page per signal that was at any point evaluated — including signals in the **graveyard**, so failed ideas aren't unconsciously retried.

## Frontmatter

```yaml
---
signal_id: volume_anomaly_5_60_t2.0        # stable identifier, matches signal_runs.signal_name
status: validated                          # validated | borderline | graveyard | deprecated
hold_days: 30
data_sources:                              # tagged: db:<table> | external:<source-name>
  - db:prices
validated_run_id: 2                        # the run_id in signal_runs that established status
code_version: 5b6e8f1                      # git short-hash of the implementation at validation time — required for reproducibility
event_max_date: 2024-12-31                 # iteration window end — proves holdout discipline
lifecycle: validated                       # draft | validated | reviewed
last_updated: 2026-05-04                   # auto
last_reviewed: 2026-05-04                  # CURATOR-ONLY
freshness_status: current                  # current | stale | needs_review
confidence: medium                         # low | medium | high
schema_version: 1
---
```

Status semantics:

- **validated** — passes the bar in STRATEGY.md (N ≥ 30, p_alpha_vs_sector < 0.05) on the iteration window AND on the 2025 holdout once tested.
- **borderline** — passes the iteration window but with p ∈ [0.05, 0.10], or fails-by-a-hair. Treated as not-tradeable, kept for context.
- **graveyard** — failed validation. Stays so the idea isn't retried without remembering why it died.
- **deprecated** — was validated, has since stopped working or been replaced by a successor. Keep history.

**Default confidence on first validation:**

| Status | Default `confidence` |
| --- | --- |
| `validated` (passes both iteration AND holdout) | `high` |
| `validated` (passes iteration, holdout pending) | `medium` |
| `borderline` | `medium` |
| `graveyard` / `deprecated` | `low` |

The Validator does not set `confidence` (curator-only field). The table is the *expected baseline* — drift from it is fine but logs an entry in §7 Decision history with the reason.

`data_sources` format:

- Each entry is a tagged string: `db:<duckdb_table>` or `external:<source_name>`.
- Examples: `db:prices`, `db:sec_form4`, `external:edgar`, `external:yfinance`.
- Validator Pass 1 enforces the `db:` / `external:` prefix and rejects bare names.

## Required sections

Each section has a default `claim_type` (see `schemas/VALIDATOR_RULES.md`).

### 1. Definition (the most important section)
**Default claim_type:** `factual_claim` — points to the implementation file as the authoritative source

A single, codeable definition. If a smart reader can't write the SQL/pandas from this section, it isn't done.

```
Event: a (ticker, date) where the 5-day mean trading volume divided by the
60-day median trading volume exceeds 2.0, and at least 5 calendar days have
passed since the previous firing on that ticker (debounce).

Inputs: prices.volume (DuckDB)
Output: events DataFrame with columns: ticker, event_date, ratio
Implementation: src/signalalpha/signals/volume_anomaly.py::detect
```

### 2. Validation summary
**Default claim_type:** `signal_summary` — auto-generated, cites `signal_run:N`

Pulled from `signal_runs` row referenced by `validated_run_id`. Auto-generated; do not hand-edit. Wrapped in `<!-- AUTOGEN:BEGIN validation_summary --> ... <!-- AUTOGEN:END validation_summary -->` markers per the auto-generator rules in `AGENTS.md`.

```
Run #2 — 2026-05-03
N events: 1480 (window 2018-03-28 → 2024-12-24, 2025 held out)
Hit rate: 54.4%
Mean return: +3.14% over 30 trading days
Mean alpha vs SOXX/ITA/IYZ (per-event): +1.37%
p-value vs sector: 0.0308 — below 0.05 bar — VALIDATED
Sharpe (annualized): 0.35
Max drawdown of sequential equity curve: -100% (signal would not be sized all-in in practice)
```

### 3. Why it might work (≤ 100 words; Validator WARNs at >120)
**Default claim_type:** `interpretation`

The economic intuition. Not required to be airtight, but required to exist — otherwise we're curve-fitting. Budget is a guideline, not a contract — Validator only WARNs.

### 4. Known limitations
**Default claim_type:** `risk_note`

```
- Top firing tickers skew to small/volatile names (SPCE, ASTS, GSAT, SATS).
  Performance on liquid megacaps may be weaker — stratified backtest pending.
- "No news within 3 days" filter is NOT applied yet; results may include
  earnings-driven volume which overlaps with the earnings_surprise signal.
- 60-day median can be skewed by extended high-volume regimes.
```

### 5. Comparable signals
**Default claim_type:** `factual_claim` — each link points to a signal page

Links to related signals in the wiki, including the ones it's most easily confused with.

```
- earnings_surprise_q75 (graveyard) — overlaps when volume spikes are earnings-driven
- 8k_excl_earnings (borderline) — overlaps when volume spikes coincide with material agreements
```

### 6. When to use / when NOT to use
**Default claim_type:** `interpretation`

```
USE when: a name in the universe shows a daily fire and no concurrent earnings/8-K.
DO NOT use when: the firing ticker is a top-firing-rate name (>50 firings in window) —
                 those are noise-prone.
```

### 7. Decision history
**Default claim_type:** `factual_claim` — every entry is dated and traceable

Append-only log of state changes.

```
- 2026-05-03 — created and validated. run_id=2.
- 2026-05-03 — observed top-firing-tickers skew; flagged as limitation §4.
```

## Graveyard variant

Signals with `status: graveyard` use the same schema, with these differences:

- `validated_run_id` points to the run that established failure.
- Section 2 explicitly states why it failed (which bar was missed by how much).
- Section 7 contains the **autopsy**: why we thought it would work, why it didn't.

Example for `earnings_surprise_q75` (failed):

```
Status: graveyard
Why failed: 60d run_id=4. p-value vs sector = 0.46 — far above 0.05 bar. Mean alpha
            +1.13% but with std=32% the signal is indistinguishable from noise on
            this sample. Predicted in Week 1 PEAD smoke test (modern megacap PEAD
            is in the noise; sample size too small).
```

## Anti-patterns

- **Tweaking thresholds to pass the bar.** Multiple-testing kills you. New thresholds = new signal_id.
- **Restating the validation result without the limitations section.** A signal page without a "Known limitations" section is not done.
- **Removing graveyard pages.** Past failures are the most valuable content — don't delete.
