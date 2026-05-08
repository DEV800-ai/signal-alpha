"""Run validated signals on all available data (no date cap).

Called weekly after price ingestion to keep the dashboard current.
Each call creates a new signal_run record — the top10 query uses only
the latest run per signal_name, so old runs are automatically superseded.
"""
from __future__ import annotations

from signalalpha.backtest import backtest, record_result
from signalalpha.signals import volume_anomaly
from signalalpha.signals.patent_cluster import detect as patent_detect

LIVE_SPECS = [
    {
        "name":   "volume_anomaly_5_60_t2.0__hold10d",
        "hold":   10,
        "params": {"threshold": 2.0, "window_short": 5, "window_long": 60, "hold_days": 10},
    },
    {
        "name":   "volume_anomaly_5_60_t2.0__hold15d",
        "hold":   15,
        "params": {"threshold": 2.0, "window_short": 5, "window_long": 60, "hold_days": 15},
    },
    {
        "name":   "volume_anomaly_5_60_t2.0__hold20d",
        "hold":   20,
        "params": {"threshold": 2.0, "window_short": 5, "window_long": 60, "hold_days": 20},
    },
]


def run_live_signals() -> list[dict]:
    """Detect + backtest all validated signals on all available data. Returns summary rows."""
    results = []

    # ── Volume anomaly (3 hold periods) ───────────────────────────────────────
    events_vol = volume_anomaly.detect(threshold=2.0, window_short=5, window_long=60)
    for spec in LIVE_SPECS:
        result = backtest(events_vol, hold_days=spec["hold"], signal_name=spec["name"])
        run_id = record_result(result, params=spec["params"], notes="live weekly re-run")
        results.append({
            "signal_name": spec["name"],
            "run_id":      run_id,
            "n_events":    result.n_events,
            "alpha":       round(result.mean_alpha_sector * 100, 2),
            "p_value":     round(result.p_value_vs_sector, 4) if result.p_value_vs_sector else None,
        })

    # ── Patent cluster — telecom, 45d hold ────────────────────────────────────
    patent_params = {
        "sectors": ["telecom"], "min_grants": 5,
        "window_days": 30, "debounce_days": 30, "hold_days": 45,
    }
    events_patent = patent_detect(
        min_grants=5, window_days=30, debounce_days=30, sectors=("telecom",)
    )
    result = backtest(
        events_patent, hold_days=45,
        signal_name="patent_cluster_telecom_n5_w30d_hold45",
    )
    run_id = record_result(result, params=patent_params, notes="live weekly re-run")
    results.append({
        "signal_name": "patent_cluster_telecom_n5_w30d_hold45",
        "run_id":      run_id,
        "n_events":    result.n_events,
        "alpha":       round(result.mean_alpha_sector * 100, 2),
        "p_value":     round(result.p_value_vs_sector, 4) if result.p_value_vs_sector else None,
    })

    return results
