"""Backtest framework with point-in-time guardrails.

A signal is a set of (ticker, event_date) rows. The backtest answers:
- If we entered at the next trading day's open after each event,
- Held for `hold_days` *trading* days, then exited at the open,
- After paying a slippage cost round-trip,
- What was the distribution of returns, vs. the relevant sector ETF,
  vs. SPY, with what statistical significance?

Guardrails:
- Entry is the next trading day strictly after event_date — no look-ahead.
- Sector mapping comes from the universe table; benchmarks from config.
- Round-trip slippage default 10 bps, applied as a deduction to gross return.
- Events whose exit day falls beyond the available price history are dropped.
- Events on tickers with no price data are dropped.
- Per-event sector / SPY returns use the same entry/exit dates.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from signalalpha.config import BROAD_BENCHMARK, SECTOR_BENCHMARKS
from signalalpha.db import connect


@dataclass
class BacktestResult:
    signal_name: str
    hold_days: int
    n_events: int
    n_dropped: int
    sample_period: tuple[dt.date, dt.date] | None
    hit_rate: float
    mean_return: float
    median_return: float
    std_return: float
    sharpe_ann: float
    max_drawdown: float
    mean_alpha_sector: float
    mean_alpha_spy: float
    hit_rate_vs_sector: float
    p_value_vs_zero: float
    p_value_vs_sector: float
    events: pd.DataFrame = field(repr=False)
    inflight_events: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)

    def summary(self) -> str:
        if self.n_events == 0:
            return f"[{self.signal_name}] no valid events (dropped={self.n_dropped})"
        return (
            f"[{self.signal_name}] hold={self.hold_days}d  N={self.n_events} (dropped={self.n_dropped})\n"
            f"  hit_rate          = {self.hit_rate:6.1%}\n"
            f"  mean_return       = {self.mean_return:+7.2%}   median={self.median_return:+7.2%}   std={self.std_return:6.2%}\n"
            f"  sharpe (annual.)  = {self.sharpe_ann:6.2f}\n"
            f"  max_drawdown      = {self.max_drawdown:6.1%}\n"
            f"  mean alpha vs sec = {self.mean_alpha_sector:+7.2%}   hit-vs-sector = {self.hit_rate_vs_sector:6.1%}\n"
            f"  mean alpha vs SPY = {self.mean_alpha_spy:+7.2%}\n"
            f"  p (mean != 0)     = {self.p_value_vs_zero:6.4f}\n"
            f"  p (alpha vs sec)  = {self.p_value_vs_sector:6.4f}\n"
            f"  sample period     = {self.sample_period[0]} → {self.sample_period[1]}"
        )


def _load_prices(con) -> dict[str, pd.DataFrame]:
    """Return ticker -> DataFrame[date, open, close] sorted by date with a
    sequential trading-day index (`tday`) for O(1) hold-period offsets."""
    raw = con.execute(
        "SELECT ticker, date, open, close FROM prices ORDER BY ticker, date"
    ).fetchdf()
    out: dict[str, pd.DataFrame] = {}
    for tkr, g in raw.groupby("ticker", sort=False):
        g = g.reset_index(drop=True)
        g["tday"] = np.arange(len(g))
        out[tkr] = g
    return out


def _load_sector_map(con) -> dict[str, str]:
    return dict(con.execute("SELECT ticker, sector FROM universe").fetchall())


def _entry_exit(prices: pd.DataFrame, event_date: pd.Timestamp, hold_days: int) -> tuple | None:
    """Return (entry_date, entry_open, exit_date, exit_open) or None if not feasible.
    Entry is the first trading day strictly AFTER event_date.
    Returns (entry_date, entry_open, None, None) when entry is available but
    the hold period extends beyond available price history (in-flight signal)."""
    after = prices[prices["date"] > event_date]
    if after.empty:
        return None
    entry_row = after.iloc[0]
    entry_tday = int(entry_row["tday"])
    exit_tday = entry_tday + hold_days
    if exit_tday >= len(prices):
        return (entry_row["date"], float(entry_row["open"]), None, None)
    exit_row = prices.iloc[exit_tday]
    return (
        entry_row["date"],
        float(entry_row["open"]),
        exit_row["date"],
        float(exit_row["open"]),
    )


def _gross_to_net(gross: float, slippage_bps: float) -> float:
    """Subtract round-trip slippage cost (bps) from a gross return."""
    return gross - slippage_bps / 1e4


def _max_drawdown(returns: Iterable[float]) -> float:
    """Sequential equity curve drawdown: treats events as time-ordered all-in trades.
    Returns a non-positive number (worst peak-to-trough)."""
    eq = np.cumprod(1.0 + np.asarray(list(returns)))
    if len(eq) == 0:
        return 0.0
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max
    return float(dd.min())


def backtest(
    events: pd.DataFrame,
    hold_days: int,
    *,
    signal_name: str = "unnamed",
    slippage_bps: float = 10.0,
    min_n: int = 30,
    event_max_date: str | pd.Timestamp | None = None,
) -> BacktestResult:
    """Run a backtest on an event table.

    events: DataFrame with columns ['ticker', 'event_date'] (date or datetime).
            Extra columns are passed through to the per-event detail.
    hold_days: trading-day hold period.
    event_max_date: drop events after this date. Use config.ITERATION_END to
        enforce the 2025 holdout during signal development.
    """
    if not {"ticker", "event_date"}.issubset(events.columns):
        raise ValueError("events must have columns: ticker, event_date")
    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    if event_max_date is not None:
        cutoff = pd.Timestamp(event_max_date)
        ev = ev[ev["event_date"] <= cutoff].copy()
    ev = ev.sort_values("event_date").reset_index(drop=True)

    con = connect(read_only=True)
    try:
        prices = _load_prices(con)
        sector_map = _load_sector_map(con)
    finally:
        con.close()

    rows = []
    inflight_rows = []
    n_dropped = 0
    for r in ev.itertuples(index=False):
        tkr = r.ticker
        d = r.event_date
        if tkr not in prices:
            n_dropped += 1
            continue
        stock = _entry_exit(prices[tkr], d, hold_days)
        if stock is None:
            n_dropped += 1
            continue
        entry_date, entry_px, exit_date, exit_px = stock
        if exit_date is None:
            # In-flight: entry is available but hold period extends beyond price history
            sector = sector_map.get(tkr)
            bench_tkr = SECTOR_BENCHMARKS.get(sector) if sector else None
            inflight_rows.append({
                "ticker": tkr,
                "event_date": d,
                "entry_date": entry_date,
                "entry_px": entry_px,
                "sector_benchmark": bench_tkr,
            })
            continue
        gross = exit_px / entry_px - 1.0
        net = _gross_to_net(gross, slippage_bps)

        sector = sector_map.get(tkr)
        bench_tkr = SECTOR_BENCHMARKS.get(sector) if sector else None
        sec_ret = _aligned_return(prices, bench_tkr, entry_date, exit_date) if bench_tkr else np.nan
        spy_ret = _aligned_return(prices, BROAD_BENCHMARK, entry_date, exit_date)

        rows.append(
            {
                "ticker": tkr,
                "event_date": d,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_px": entry_px,
                "exit_px": exit_px,
                "gross_return": gross,
                "net_return": net,
                "sector_benchmark": bench_tkr,
                "sector_return": sec_ret,
                "spy_return": spy_ret,
            }
        )

    detail = pd.DataFrame(rows)
    inflight = pd.DataFrame(inflight_rows)
    n = len(detail)
    if n == 0:
        return BacktestResult(
            signal_name=signal_name, hold_days=hold_days, n_events=0,
            n_dropped=n_dropped, sample_period=None,
            hit_rate=float("nan"), mean_return=float("nan"), median_return=float("nan"),
            std_return=float("nan"), sharpe_ann=float("nan"), max_drawdown=float("nan"),
            mean_alpha_sector=float("nan"), mean_alpha_spy=float("nan"),
            hit_rate_vs_sector=float("nan"),
            p_value_vs_zero=float("nan"), p_value_vs_sector=float("nan"),
            events=detail,
            inflight_events=inflight,
        )

    nr = detail["net_return"].to_numpy()
    sec = detail["sector_return"].to_numpy()
    spy = detail["spy_return"].to_numpy()
    alpha_sec = nr - sec
    alpha_spy = nr - spy

    mean = float(np.nanmean(nr))
    std = float(np.nanstd(nr, ddof=1)) if n > 1 else float("nan")
    # Annualize Sharpe assuming hold_days trading-day periods, ~252 td/year.
    if std and std > 0:
        sharpe_ann = (mean / std) * np.sqrt(252.0 / hold_days)
    else:
        sharpe_ann = float("nan")

    p_zero = float(stats.ttest_1samp(nr, 0.0, nan_policy="omit").pvalue) if n > 1 else float("nan")
    sec_mask = ~np.isnan(sec)
    if sec_mask.sum() > 1:
        p_sec = float(stats.ttest_rel(nr[sec_mask], sec[sec_mask]).pvalue)
    else:
        p_sec = float("nan")

    result = BacktestResult(
        signal_name=signal_name,
        hold_days=hold_days,
        n_events=n,
        n_dropped=n_dropped,
        sample_period=(detail["event_date"].min(), detail["event_date"].max()),
        hit_rate=float((nr > 0).mean()),
        mean_return=mean,
        median_return=float(np.nanmedian(nr)),
        std_return=std,
        sharpe_ann=sharpe_ann,
        max_drawdown=_max_drawdown(nr),
        mean_alpha_sector=float(np.nanmean(alpha_sec)),
        mean_alpha_spy=float(np.nanmean(alpha_spy)),
        hit_rate_vs_sector=float((alpha_sec > 0)[sec_mask].mean()) if sec_mask.any() else float("nan"),
        p_value_vs_zero=p_zero,
        p_value_vs_sector=p_sec,
        events=detail,
        inflight_events=inflight,
    )
    if n < min_n:
        result.signal_name = f"{signal_name} [WARN: N<{min_n}, treat with skepticism]"
    return result


def record_result(result: BacktestResult, params: dict | None = None, notes: str = "") -> int:
    """Persist a backtest result to signal_runs + signal_events. Returns the run_id."""
    import json
    import math

    con = connect()
    try:
        ws = result.sample_period[0] if result.sample_period else None
        we = result.sample_period[1] if result.sample_period else None
        cur = con.execute(
            """
            INSERT INTO signal_runs (
                signal_name, hold_days, event_window_start, event_window_end,
                n_events, n_dropped, hit_rate, mean_return, median_return,
                std_return, sharpe_ann, max_drawdown, mean_alpha_sector,
                mean_alpha_spy, hit_rate_vs_sector, p_value_vs_zero,
                p_value_vs_sector, params_json, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING run_id
            """,
            [
                result.signal_name, result.hold_days, ws, we,
                result.n_events, result.n_dropped, result.hit_rate,
                result.mean_return, result.median_return, result.std_return,
                result.sharpe_ann, result.max_drawdown, result.mean_alpha_sector,
                result.mean_alpha_spy, result.hit_rate_vs_sector,
                result.p_value_vs_zero, result.p_value_vs_sector,
                json.dumps(params or {}), notes,
            ],
        )
        run_id = cur.fetchone()[0]

        if not result.events.empty:
            def _f(v):
                if v is None:
                    return None
                try:
                    return None if math.isnan(float(v)) else float(v)
                except (TypeError, ValueError):
                    return None

            ev = result.events.copy()
            nr = ev["net_return"].to_numpy(dtype=float)
            sr = ev["sector_return"].to_numpy(dtype=float) if "sector_return" in ev.columns else [float("nan")] * len(ev)
            sp = ev["spy_return"].to_numpy(dtype=float) if "spy_return" in ev.columns else [float("nan")] * len(ev)

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

        if not result.inflight_events.empty:
            inf = result.inflight_events.copy()
            inflight_rows = [
                (
                    run_id,
                    str(r.ticker),
                    r.event_date.date() if hasattr(r.event_date, "date") else r.event_date,
                    r.entry_date.date() if hasattr(r.entry_date, "date") else r.entry_date,
                    None,  # exit_date
                    _f(r.entry_px), None,  # exit_px
                    None, None,  # gross_return, net_return
                    str(r.sector_benchmark) if r.sector_benchmark and str(r.sector_benchmark) != "nan" else None,
                    None, None, None, None,  # sector_return, spy_return, alpha_sector, alpha_spy
                )
                for r in inf.itertuples(index=False)
            ]
            con.executemany(
                """INSERT INTO signal_events (
                    run_id, ticker, event_date, entry_date, exit_date,
                    entry_px, exit_px, gross_return, net_return,
                    sector_benchmark, sector_return, spy_return,
                    alpha_sector, alpha_spy
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                inflight_rows,
            )

        return int(run_id)
    finally:
        con.close()


def _aligned_return(
    prices: dict[str, pd.DataFrame],
    bench_ticker: str | None,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> float:
    """Open-to-open return on bench_ticker for the same entry/exit dates as the trade.
    If exact dates aren't traded for the benchmark, fall back to nearest-on-or-after."""
    if not bench_ticker or bench_ticker not in prices:
        return float("nan")
    p = prices[bench_ticker]
    e = p[p["date"] >= entry_date]
    x = p[p["date"] >= exit_date]
    if e.empty or x.empty:
        return float("nan")
    return float(x.iloc[0]["open"] / e.iloc[0]["open"] - 1.0)
