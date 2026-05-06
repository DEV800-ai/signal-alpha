"""Holdout validation — one-time out-of-sample test.

⚠️  THIS IS A ONE-WAY DOOR.
    Results must be accepted as-is. Do not re-iterate parameters based
    on holdout outcomes. If a signal fails here, it goes to the graveyard
    regardless of in-sample performance.

Holdout window: 2025-01-01 → present (data available to 2026-05-01).
In-sample window: 2018-01-01 → 2024-12-31 (used for all prior development).

Signals tested:
  1. volume_anomaly_5_60_t2.0 @ 15d hold  — primary (best p + Sharpe in-sample)
  2. volume_anomaly_5_60_t2.0 @ 10d hold  — secondary (highest in-sample Sharpe)
  3. 8k_excl_earnings           @ 30d hold  — borderline in-sample (p=0.053)
"""
from __future__ import annotations

import math

import pandas as pd

from signalalpha.backtest import backtest, record_result
from signalalpha.config import HOLDOUT_START
from signalalpha.signals import filing_8k, volume_anomaly

HOLDOUT_MIN = HOLDOUT_START  # "2025-01-01"

IN_SAMPLE = {
    "volume_anomaly_15d": {"n": 1480, "alpha": 0.01270, "sharpe": 0.49, "p": 0.0046},
    "volume_anomaly_10d": {"n": 1480, "alpha": 0.01100, "sharpe": 0.50, "p": 0.0061},
    "8k_excl_earnings":   {"n": 3754, "alpha": 0.00460, "sharpe": 0.37, "p": 0.0529},
}

SPECS = [
    {
        "label":   "volume_anomaly_15d",
        "name":    "volume_anomaly_5_60_t2.0__holdout_15d",
        "detect":  lambda: volume_anomaly.detect(threshold=2.0, window_short=5, window_long=60),
        "hold":    15,
        "params":  {"threshold": 2.0, "window_short": 5, "window_long": 60, "hold_days": 15},
    },
    {
        "label":   "volume_anomaly_10d",
        "name":    "volume_anomaly_5_60_t2.0__holdout_10d",
        "detect":  lambda: volume_anomaly.detect(threshold=2.0, window_short=5, window_long=60),
        "hold":    10,
        "params":  {"threshold": 2.0, "window_short": 5, "window_long": 60, "hold_days": 10},
    },
    {
        "label":   "8k_excl_earnings",
        "name":    "8k_excl_earnings__holdout_30d",
        "detect":  lambda: filing_8k.detect(exclude_earnings=True),
        "hold":    30,
        "params":  {"exclude_earnings": True, "hold_days": 30},
    },
]


def verdict(result) -> str:
    p = result.p_value_vs_sector
    if result.n_events < 20 or p is None or math.isnan(p):
        return "INCONCLUSIVE"
    if p < 0.05:
        return "PASS"
    if p < 0.10:
        return "BORDERLINE"
    return "FAIL"


def direction_check(result, label: str) -> str:
    """Did the signal fire in the right direction vs in-sample?"""
    insample = IN_SAMPLE[label]
    alpha_sign_ok  = result.mean_alpha_sector > 0
    return_sign_ok = result.mean_return > 0
    alpha_ratio    = result.mean_alpha_sector / insample["alpha"] if insample["alpha"] else 0
    return (
        f"alpha {'✓' if alpha_sign_ok else '✗'} "
        f"({'%.0f' % (alpha_ratio * 100)}% of in-sample)  "
        f"return {'✓' if return_sign_ok else '✗'}"
    )


def main() -> None:
    print("=" * 72)
    print("HOLDOUT VALIDATION  —  2025-01-01 → 2026-05-01")
    print("⚠️  One-time out-of-sample test. Results are final.")
    print("=" * 72)

    summary_rows = []

    for spec in SPECS:
        label = spec["label"]
        print(f"\n{'─' * 72}")
        print(f"Signal: {label}  (hold={spec['hold']}d)")

        events_all = spec["detect"]()
        events = events_all[events_all["event_date"] >= HOLDOUT_MIN].copy()
        print(f"  Raw events in holdout window: {len(events)}")

        result = backtest(
            events,
            hold_days=spec["hold"],
            signal_name=spec["name"],
        )
        print(result.summary())

        v = verdict(result)
        dc = direction_check(result, label)
        print(f"\n  HOLDOUT VERDICT: {v}")
        print(f"  Direction check: {dc}")

        # Compare key stats
        ins = IN_SAMPLE[label]
        p = result.p_value_vs_sector
        print(f"\n  ┌─────────────────────────────────────────┐")
        print(f"  │ Metric      In-sample    Holdout         │")
        print(f"  │ N           {ins['n']:>9}    {result.n_events:>9}       │")
        print(f"  │ Alpha       {ins['alpha']*100:>+8.2f}%    {result.mean_alpha_sector*100:>+8.2f}%       │")
        print(f"  │ Sharpe      {ins['sharpe']:>9.2f}    {result.sharpe_ann:>9.2f}       │")
        print(f"  │ p-value     {ins['p']:>9.4f}    {p:>9.4f}       │")
        print(f"  └─────────────────────────────────────────┘")

        run_id = record_result(
            result,
            params={**spec["params"], "holdout": True, "holdout_start": HOLDOUT_MIN},
            notes=f"HOLDOUT {v} | {label} out-of-sample 2025+",
        )
        summary_rows.append({
            "signal":         label,
            "hold":           spec["hold"],
            "N_holdout":      result.n_events,
            "alpha_insample": f"{ins['alpha']*100:+.2f}%",
            "alpha_holdout":  f"{result.mean_alpha_sector*100:+.2f}%",
            "p_insample":     f"{ins['p']:.4f}",
            "p_holdout":      f"{p:.4f}" if p and not math.isnan(p) else "—",
            "sharpe_holdout": f"{result.sharpe_ann:.2f}",
            "verdict":        v,
            "run_id":         run_id,
        })

    print(f"\n{'#' * 72}")
    print("# HOLDOUT SUMMARY")
    print(f"{'#' * 72}")
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
