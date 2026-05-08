"""Run patent-grant cluster signal backtest.

Step 1: ingest patent grants (PatentsView API) if not already done.
Step 2: detect clusters (≥5 grants in 30-day window).
Step 3: backtest — entry T+1 open, hold 30 days, compare vs sector ETF.

This is an in-sample run (2018–2024). The 2025+ holdout is reserved.
"""
from __future__ import annotations

import math

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.ingest_patents import ingest_all
from signalalpha.signals.patent_cluster import detect

SIGNAL_NAME = "patent_cluster_n5_w30d"
HOLD_DAYS = 30
PARAMS = {
    "min_grants":    5,
    "window_days":   30,
    "debounce_days": 30,
    "hold_days":     HOLD_DAYS,
}


def main() -> None:
    print("=" * 72)
    print("Patent-Grant Cluster Signal — in-sample run (2018–2024)")
    print("=" * 72)

    print("\nStep 1 — Ingesting patent grants from PatentsView …")
    ingest_all()

    print("\nStep 2 — Detecting clusters (≥5 grants / 30-day window) …")
    events = detect(min_grants=5, window_days=30, debounce_days=30)
    print(f"  Raw events: {len(events)}")
    if not events.empty:
        print(f"  Tickers with events: {events['ticker'].nunique()}")
        print(f"  Date range: {events['event_date'].min()} → {events['event_date'].max()}")

    print("\nStep 3 — Backtesting …")
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
    verdict = "PASS" if passed else ("BORDERLINE" if p and p < 0.10 else "GRAVEYARD")
    notes = f"{verdict} | patent cluster ≥5 grants / 30d window, 30d hold"

    run_id = record_result(result, params=PARAMS, notes=notes)
    print(f"\n  VERDICT: {verdict}   (run_id={run_id})")
    print(f"  p (alpha vs sector) = {p:.4f}" if p and not math.isnan(p) else "  p = N/A")


if __name__ == "__main__":
    main()
