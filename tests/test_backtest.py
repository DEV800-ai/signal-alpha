"""Unit tests for the backtest framework.

These tests use the live DuckDB. Run after `python -m signalalpha.ingest_prices`.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from signalalpha.backtest import backtest
from signalalpha.db import connect


@pytest.fixture(scope="module")
def have_data() -> bool:
    con = connect(read_only=True)
    n = con.execute("SELECT count(*) FROM prices").fetchone()[0]
    con.close()
    return n > 0


def test_single_event_returns_one_row(have_data: bool) -> None:
    if not have_data:
        pytest.skip("No price data ingested")
    events = pd.DataFrame({"ticker": ["NVDA"], "event_date": [pd.Timestamp("2023-01-03")]})
    r = backtest(events, hold_days=30, signal_name="t1")
    assert r.n_events == 1
    assert r.n_dropped == 0
    row = r.events.iloc[0]
    assert row["entry_date"] > pd.Timestamp("2023-01-03")
    assert row["exit_date"] > row["entry_date"]
    assert row["entry_px"] > 0 and row["exit_px"] > 0
    # Net return = gross return - 0.001 (10 bps)
    assert math.isclose(row["net_return"], row["gross_return"] - 0.001, abs_tol=1e-9)


def test_unknown_ticker_is_dropped(have_data: bool) -> None:
    if not have_data:
        pytest.skip("No price data ingested")
    events = pd.DataFrame({
        "ticker": ["NVDA", "ZZZZ_FAKE"],
        "event_date": [pd.Timestamp("2023-01-03"), pd.Timestamp("2023-01-03")],
    })
    r = backtest(events, hold_days=30, signal_name="t2")
    assert r.n_events == 1
    assert r.n_dropped == 1


def test_event_too_recent_is_dropped(have_data: bool) -> None:
    if not have_data:
        pytest.skip("No price data ingested")
    # An event "yesterday" with a 60-day hold has no exit yet
    yesterday = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    events = pd.DataFrame({"ticker": ["NVDA"], "event_date": [yesterday]})
    r = backtest(events, hold_days=60, signal_name="t3")
    assert r.n_events == 0
    assert r.n_dropped == 1


def test_sector_mapping_picks_right_benchmark(have_data: bool) -> None:
    if not have_data:
        pytest.skip("No price data ingested")
    # NVDA is ai_infra → SOXX; LMT is space_defense → ITA
    events = pd.DataFrame({
        "ticker": ["NVDA", "LMT"],
        "event_date": [pd.Timestamp("2023-01-03"), pd.Timestamp("2023-01-03")],
    })
    r = backtest(events, hold_days=30, signal_name="t4")
    benches = dict(zip(r.events["ticker"], r.events["sector_benchmark"]))
    assert benches["NVDA"] == "SOXX"
    assert benches["LMT"] == "ITA"


def test_n_warning_below_threshold(have_data: bool) -> None:
    if not have_data:
        pytest.skip("No price data ingested")
    events = pd.DataFrame({"ticker": ["NVDA"], "event_date": [pd.Timestamp("2023-01-03")]})
    r = backtest(events, hold_days=30, signal_name="t5", min_n=30)
    assert "WARN" in r.signal_name
