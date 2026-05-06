"""Week 2 final: run every signal, persist results, print a verdict table.

Validation bar (per STRATEGY.md):
  - N >= 30 events in 2018-2024
  - Mean alpha vs sector with p < 0.05
  - 2025 holdout NOT touched here

Signals that fail go to the graveyard with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.signals import earnings_surprise, filing_8k, insider_buy, volume_anomaly


@dataclass
class SignalSpec:
    name: str
    hold_days: int
    detector: callable
    detector_kwargs: dict
    rationale: str  # one-liner of what we're testing


SPECS = [
    SignalSpec(
        name="volume_anomaly_5_60_t2.0",
        hold_days=30,
        detector=volume_anomaly.detect,
        detector_kwargs={"threshold": 2.0, "window_short": 5, "window_long": 60},
        rationale="5-day vol > 2x 60-day median, debounced",
    ),
    SignalSpec(
        name="earnings_surprise_q75",
        hold_days=60,
        detector=earnings_surprise.detect,
        detector_kwargs={"quantile": 0.75},
        rationale="Top-quartile positive EPS surprise, BMO-adjusted, 60d hold",
    ),
    SignalSpec(
        name="8k_excl_earnings",
        hold_days=30,
        detector=filing_8k.detect,
        detector_kwargs={"exclude_earnings": True},
        rationale="Any 8-K except routine earnings",
    ),
    SignalSpec(
        name="insider_buy_100k",
        hold_days=90,
        detector=insider_buy.detect,
        detector_kwargs={"min_usd": 100_000.0},
        rationale="Aggregate Form 4 open-market purchase >= $100k per filing day",
    ),
]


VALIDATION_BAR = {"min_n": 30, "max_p_alpha": 0.05}


def main() -> None:
    summary_rows = []
    for spec in SPECS:
        events = spec.detector(**spec.detector_kwargs)
        # earnings_surprise returns (events, threshold) — others return events directly
        if isinstance(events, tuple):
            events, _meta = events
        result = backtest(
            events,
            hold_days=spec.hold_days,
            signal_name=spec.name,
            event_max_date=ITERATION_END,
        )
        passed = (
            result.n_events >= VALIDATION_BAR["min_n"]
            and not pd.isna(result.p_value_vs_sector)
            and result.p_value_vs_sector < VALIDATION_BAR["max_p_alpha"]
        )
        verdict = "PASS" if passed else "GRAVEYARD"
        notes = f"{verdict} | {spec.rationale}"
        run_id = record_result(result, params=spec.detector_kwargs, notes=notes)
        print(f"\n{'=' * 72}")
        print(result.summary())
        print(f"  verdict           = {verdict}    (run_id={run_id})")
        summary_rows.append({
            "signal": spec.name,
            "hold": spec.hold_days,
            "N": result.n_events,
            "alpha_vs_sector": f"{result.mean_alpha_sector:+.2%}",
            "p_alpha": f"{result.p_value_vs_sector:.4f}",
            "verdict": verdict,
        })

    print(f"\n{'#' * 72}\n# WEEK 2 VERDICT TABLE\n{'#' * 72}")
    print(pd.DataFrame(summary_rows).to_string(index=False))


if __name__ == "__main__":
    main()
