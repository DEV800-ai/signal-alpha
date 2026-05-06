"""Project paths and constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "signalalpha.duckdb"
UNIVERSE_CSV = DATA_DIR / "universe.csv"

PRICE_HISTORY_START = "2018-01-01"

# Hold-out: 2025-01-01 onward is reserved for the final out-of-sample check.
# All Week-2/3 iteration backtests must cap event_date at HOLDOUT_START - 1 day.
HOLDOUT_START = "2025-01-01"
ITERATION_END = "2024-12-31"

EDGAR_USER_AGENT = "SignalAlpha personal-research pinto2004@gmail.com"

SECTOR_BENCHMARKS: dict[str, str] = {
    "ai_infra": "SOXX",
    "space_defense": "ITA",
    "telecom": "IYZ",
}
BROAD_BENCHMARK = "SPY"
