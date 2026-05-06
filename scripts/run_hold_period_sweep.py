"""Hold period sweep on the two validated/borderline signals.

Tests hold periods: 5, 10, 15, 20, 30 days.
Signals: volume_anomaly_5_60_t2.0 and 8k_excl_earnings.

Hypothesis: information events are priced in faster than 30 days.
A shorter hold may improve Sharpe and tighten p-values.
"""
from __future__ import annotations

import math

import pandas as pd

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.signals import filing_8k, volume_anomaly

HOLD_PERIODS = [5, 10, 15, 20, 30]

SIGNALS = [
    {
        "name":    "volume_anomaly_5_60_t2.0",
        "detect":  lambda: volume_anomaly.detect(threshold=2.0, window_short=5, window_long=60),
        "params":  {"threshold": 2.0, "window_short": 5, "window_long": 60},
    },
    {
        "name":    "8k_excl_earnings",
        "detect":  lambda: filing_8k.detect(exclude_earnings=True),
        "params":  {"exclude_earnings": True},
    },
]


def verdict(result) -> str:
    p = result.p_value_vs_sector
    if result.n_events < 30 or p is None or math.isnan(p):
        return "GRAVEYARD"
    if p < 0.05:
        return "PASS"
    if p < 0.10:
        return "BORDERLINE"
    return "GRAVEYARD"


def main() -> None:
    summary_rows = []

    for sig in SIGNALS:
        print(f"\n{'=' * 72}")
        print(f"Detecting events for {sig['name']} …")
        events = sig["detect"]()
        print(f"  {len(events)} raw events")

        for hold in HOLD_PERIODS:
            name = f"{sig['name']}__hold{hold}d"
            result = backtest(
                events,
                hold_days=hold,
                signal_name=name,
                event_max_date=ITERATION_END,
            )
            v = verdict(result)
            p = result.p_value_vs_sector
            run_id = record_result(
                result,
                params={**sig["params"], "hold_days": hold},
                notes=f"{v} | hold period sweep: {hold}d hold",
            )
            summary_rows.append({
                "signal":    sig["name"],
                "hold":      hold,
                "N":         result.n_events,
                "alpha":     f"{result.mean_alpha_sector:+.2%}",
                "return":    f"{result.mean_return:+.2%}",
                "hit_rate":  f"{result.hit_rate:.1%}",
                "sharpe":    f"{result.sharpe_ann:.2f}",
                "p_alpha":   f"{p:.4f}" if p and not math.isnan(p) else "—",
                "verdict":   v,
                "run_id":    run_id,
            })
            marker = " ◀ best?" if v in ("PASS", "BORDERLINE") else ""
            print(f"  hold={hold:2d}d  N={result.n_events:4d}  "
                  f"alpha={result.mean_alpha_sector:+.2%}  "
                  f"sharpe={result.sharpe_ann:.2f}  "
                  f"p={p:.4f}  {v}{marker}")

    print(f"\n{'#' * 72}")
    print("# HOLD PERIOD SWEEP — RESULTS")
    print(f"{'#' * 72}")
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
