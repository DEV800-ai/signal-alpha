"""Run sector-scoped volume anomaly: ai_infra only.

Hypothesis: the broad volume_anomaly_5_60_t2.0 validated at p=0.031 across
all three sectors combined. ai_infra showed +4.2% avg alpha vs +2.4% in
space_defense and +2.6% in telecom. Restricting the universe to ai_infra
should yield a tighter distribution, higher alpha, and a lower p-value.
"""
from __future__ import annotations

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.signals import volume_anomaly

SIGNAL_NAME = "volume_anomaly_5_60_t2.0_ai_infra"
HOLD_DAYS   = 30
PARAMS = {
    "threshold":    2.0,
    "window_short": 5,
    "window_long":  60,
    "sectors":      ["ai_infra"],
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
        and not __import__("math").isnan(p)
        and p < 0.05
    )
    verdict = "PASS" if passed else ("BORDERLINE" if p and p < 0.10 else "GRAVEYARD")
    notes = f"{verdict} | sector-scoped volume anomaly, ai_infra only"

    run_id = record_result(result, params=PARAMS, notes=notes)
    print(f"\n  verdict = {verdict}   (run_id={run_id})")


if __name__ == "__main__":
    main()
