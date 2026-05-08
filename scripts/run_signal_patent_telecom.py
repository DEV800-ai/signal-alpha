"""Patent-grant cluster signal — telecom sector only, 45-day hold.

Grid search showed that the patent cluster signal has no edge in ai_infra
or space_defense vs their sector ETFs (alpha ~0%), but is strongly
significant in telecom (IYZ benchmark, p~0.0000 across all param combos).

Telecom companies (QCOM, IDCC, NOK, ERIC, VZ, T, ...) are IP-licensing
businesses: patent bursts directly signal licensing pipeline and competitive
moat. The effect takes ~45 trading days to fully price in.

Params chosen: min_grants=5, window=30d, debounce=30d, hold=45d.
"""
from __future__ import annotations

import math

from signalalpha.backtest import backtest, record_result
from signalalpha.config import ITERATION_END
from signalalpha.ingest_patents import ingest_all
from signalalpha.signals.patent_cluster import detect

SIGNAL_NAME = "patent_cluster_telecom_n5_w30d_hold45"
HOLD_DAYS   = 45
PARAMS = {
    "sectors":       ["telecom"],
    "min_grants":    5,
    "window_days":   30,
    "debounce_days": 30,
    "hold_days":     HOLD_DAYS,
}


def main() -> None:
    print("=" * 72)
    print("Patent-Grant Cluster Signal — telecom only, 45d hold (2018–2024)")
    print("=" * 72)

    print("\nStep 1 — Ensuring patent data is current …")
    ingest_all()

    print("\nStep 2 — Detecting clusters (≥5 grants / 30-day window, telecom) …")
    events = detect(
        min_grants=5,
        window_days=30,
        debounce_days=30,
        sectors=("telecom",),
    )
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
    notes = f"{verdict} | telecom patent cluster ≥5 grants / 30d window, 45d hold"

    run_id = record_result(result, params=PARAMS, notes=notes)
    print(f"\n  VERDICT: {verdict}   (run_id={run_id})")
    print(f"  p (alpha vs sector) = {p:.4f}" if p and not math.isnan(p) else "  p = N/A")


if __name__ == "__main__":
    main()
