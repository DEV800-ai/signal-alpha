"""Signal detectors. Each module exposes a `detect()` function that returns
an events DataFrame with at least columns: ticker, event_date.
Backtests consume these via `signalalpha.backtest.backtest()`.
"""
