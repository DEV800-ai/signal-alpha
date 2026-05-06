"""Null test: random events on the equity universe.

Purpose: confirm the framework correctly attributes returns to sector exposure.
With random events on a universe that has positive long-run drift, we EXPECT:
  - mean_return > 0 (universe drift)
  - p_value_vs_zero often significant
  - mean_alpha_sector ~= 0
  - p_value_vs_sector NOT significant (>= 0.10)

If alpha vs sector is significant, the framework is finding edge where there
is none — sector mapping or benchmark return alignment is broken.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signalalpha.backtest import backtest
from signalalpha.db import connect


def main(n_events: int = 200, seed: int = 42, hold_days: int = 30) -> None:
    con = connect(read_only=True)
    tickers = [
        r[0] for r in con.execute(
            "SELECT u.ticker FROM universe u "
            "WHERE u.sector != 'benchmark' "
            "  AND u.ticker IN (SELECT DISTINCT ticker FROM prices)"
        ).fetchall()
    ]
    con.close()

    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-06-01", "2025-06-01", freq="B")
    events = pd.DataFrame({
        "ticker": rng.choice(tickers, size=n_events),
        "event_date": rng.choice(dates, size=n_events),
    })
    r = backtest(events, hold_days=hold_days, signal_name=f"NULL_TEST_seed{seed}")
    print(r.summary())
    print()
    print("Pass criteria: mean alpha vs sector should be near zero, p (alpha vs sec) >= 0.10.")


if __name__ == "__main__":
    main()
