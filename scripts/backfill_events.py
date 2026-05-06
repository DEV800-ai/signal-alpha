"""Backfill signal_events for existing signal_runs that have no events."""
from __future__ import annotations

import math

import numpy as np

from signalalpha.backtest import backtest
from signalalpha.config import ITERATION_END
from signalalpha.db import connect
from signalalpha.signals import earnings_surprise, filing_8k, volume_anomaly


def _detect(name: str, params: dict):
    """Run the right detector with safe params."""
    if name == "volume_anomaly_5_60_t2.0":
        return volume_anomaly.detect(
            threshold=params.get("threshold", 2.0),
            window_short=params.get("window_short", 5),
            window_long=params.get("window_long", 60),
        )
    if name == "earnings_surprise_q75":
        events, _ = earnings_surprise.detect(quantile=params.get("quantile", 0.75))
        return events
    if name in ("8k_any", "8k_excl_earnings"):
        return filing_8k.detect(exclude_earnings=params.get("exclude_earnings", False))
    if name == "8k_item_1_01":
        # Filter to 8-Ks that contain item 1.01
        df = filing_8k.detect(exclude_earnings=False)
        return df[df["items_sample"].str.contains("1.01", na=False)].copy()
    return None


def _insert_events(con, run_id: int, result) -> int:
    if result.events.empty:
        return 0
    ev = result.events.copy()
    nr = ev["net_return"].to_numpy(dtype=float)
    sr = ev["sector_return"].to_numpy(dtype=float) if "sector_return" in ev.columns else np.full(len(ev), float("nan"))
    sp = ev["spy_return"].to_numpy(dtype=float) if "spy_return" in ev.columns else np.full(len(ev), float("nan"))

    def _f(v):
        try:
            return None if math.isnan(float(v)) else float(v)
        except (TypeError, ValueError):
            return None

    rows = [
        (
            run_id,
            str(r.ticker),
            r.event_date.date() if hasattr(r.event_date, "date") else r.event_date,
            r.entry_date.date() if hasattr(r.entry_date, "date") else r.entry_date,
            r.exit_date.date() if hasattr(r.exit_date, "date") else r.exit_date,
            _f(r.entry_px), _f(r.exit_px),
            _f(r.gross_return), _f(nr[i]),
            str(r.sector_benchmark) if r.sector_benchmark and str(r.sector_benchmark) != "nan" else None,
            _f(sr[i]), _f(sp[i]),
            _f(nr[i] - sr[i]), _f(nr[i] - sp[i]),
        )
        for i, r in enumerate(ev.itertuples(index=False))
    ]
    con.executemany(
        """INSERT INTO signal_events (
            run_id, ticker, event_date, entry_date, exit_date,
            entry_px, exit_px, gross_return, net_return,
            sector_benchmark, sector_return, spy_return,
            alpha_sector, alpha_spy
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return len(rows)


def main():
    import json, re

    # 1. Collect runs needing backfill (read-only, then close)
    con_r = connect(read_only=True)
    runs = con_r.execute("""
        SELECT sr.run_id, sr.signal_name, sr.hold_days, sr.params_json,
               sr.event_window_end
        FROM signal_runs sr
        LEFT JOIN signal_events se ON se.run_id = sr.run_id
        WHERE se.id IS NULL
        ORDER BY sr.run_id
    """).fetchall()
    con_r.close()

    if not runs:
        print("All runs already have events.")
        return

    def _clean(name: str) -> str:
        return re.sub(r"\s*\[.*?\]", "", name).strip()

    for run_id, raw_name, hold_days, params_json, we in runs:
        name = _clean(raw_name)
        params = json.loads(params_json or "{}")
        event_max_date = str(we) if we else ITERATION_END
        print(f"  run_id={run_id} [{name}] hold={hold_days}d ...", end=" ", flush=True)

        try:
            raw_events = _detect(name, params)
            if raw_events is None:
                print("no detector, skip")
                continue
            result = backtest(
                raw_events,
                hold_days=hold_days,
                signal_name=name,
                event_max_date=event_max_date,
            )
        except Exception as e:
            print(f"ERROR during backtest: {e}")
            continue

        # 2. Open writable connection only for insert
        try:
            con_w = connect()
            n = _insert_events(con_w, run_id, result)
            con_w.close()
            print(f"inserted {n} events")
        except Exception as e:
            print(f"ERROR during insert: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
