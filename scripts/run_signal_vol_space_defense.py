"""Run sector-scoped volume anomaly: space_defense only.

Finding from broad signal analysis:
- space_defense has the highest sector-relative alpha (+1.89%) and the
  lowest correlation with its ETF (ITA, corr=0.19).
- Volume spikes in space_defense are company-specific events, not
  sector-wide waves — contracts, launches, program awards.
- Hypothesis: isolating space_defense should produce a tighter p-value
  than the broad signal (p=0.031) since we're removing diluting noise
  from ai_infra (corr=0.61) and telecom (corr=0.34).
"""
from __future__ import annotations

import math

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.signals import volume_anomaly

SIGNAL_NAME = "volume_anomaly_5_60_t2.0_space_defense"
HOLD_DAYS   = 30
PARAMS = {
    "threshold":    2.0,
    "window_short": 5,
    "window_long":  60,
    "sectors":      ["space_defense"],
}


def main() -> None:
    print(f"Detecting events for {SIGNAL_NAME} …")
    events = volume_anomaly.detect(
        threshold=PARAMS["threshold"],
        window_short=PARAMS["window_short"],
        window_long=PARAMS["window_long"],
        sectors=tuple(PARAMS["sectors"]),
    )
    print(f"  {len(events)} raw events before backtest filtering")

    result = backtest(
        events,
        hold_days=HOLD_DAYS,
        signal_name=SIGNAL_NAME,
        event_max_date=ITERATION_END,
    )

    print(result.summary())

    p = result.p_value_vs_sector
    passed = (
        result.n_events >= 30
        and p is not None
        and not math.isnan(p)
        and p < 0.05
    )
    borderline = p is not None and not math.isnan(p) and p < 0.10
    verdict = "PASS" if passed else ("BORDERLINE" if borderline else "GRAVEYARD")
    notes = f"{verdict} | sector-scoped volume anomaly, space_defense only"

    run_id = record_result(result, params=PARAMS, notes=notes)
    print(f"\n  verdict = {verdict}   (run_id={run_id})")


if __name__ == "__main__":
    main()
