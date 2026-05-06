"""Performance smoke test — not a CI gate, just reports wall-clock time."""
from __future__ import annotations

import time
from pathlib import Path

from signalalpha.wiki.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"
THRESHOLD_MS = 500


def test_pass_all_perf(db):
    start = time.perf_counter()
    validate(FIXTURES / "volume_anomaly_pass.md", db)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms > THRESHOLD_MS:
        print(f"\n[PERF] WARNING: validate took {elapsed_ms:.1f}ms (threshold {THRESHOLD_MS}ms)")
    else:
        print(f"\n[PERF] OK: validate took {elapsed_ms:.1f}ms")
    # Do not fail CI — fixture pages are too small to be representative.
    assert True
