"""Tests for Pass 1 — Frontmatter validation."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from signalalpha.wiki.frontmatter import run_pass1

UNIVERSE = Path(__file__).parent.parent.parent / "data" / "universe.csv"
FAKE_SIGNAL = Path("/fake/wiki/signals/test.md")
TODAY = date(2026, 5, 5)


def _base_fm():
    return {
        "signal_id": "test_signal",
        "status": "validated",
        "hold_days": 30,
        "data_sources": ["db:prices"],
        "validated_run_id": 2,
        "code_version": "5b6e8f1",
        "event_max_date": "2024-12-31",
        "lifecycle": "validated",
        "last_updated": date(2026, 5, 5),
        "last_reviewed": date(2026, 5, 5),
        "freshness_status": "current",
        "confidence": "medium",
        "schema_version": 1,
    }


def test_valid_signal_passes():
    result = run_pass1(FAKE_SIGNAL, _base_fm(), "signal", TODAY, UNIVERSE)
    assert not result.failures


def test_lifecycle_integrity_fail():
    fm = _base_fm()
    fm["lifecycle"] = "reviewed"
    fm["last_updated"] = date(2026, 5, 5)
    fm["last_reviewed"] = date(2026, 4, 1)
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "lifecycle.integrity" in rules


def test_schema_version_too_high():
    fm = _base_fm()
    fm["schema_version"] = 99
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "schema_version.unsupported" in rules


def test_schema_version_too_low():
    fm = _base_fm()
    fm["schema_version"] = 0
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "schema_version.unsupported" in rules


def test_missing_required_field():
    fm = _base_fm()
    del fm["signal_id"]
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    assert any("signal_id" in f.message for f in result.failures)


def test_bad_lifecycle_enum():
    fm = _base_fm()
    fm["lifecycle"] = "published"
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "frontmatter.enum" in rules


def test_future_date_fails():
    fm = _base_fm()
    fm["last_updated"] = date(2030, 1, 1)
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "frontmatter.date_future" in rules


def test_invalid_data_source():
    fm = _base_fm()
    fm["data_sources"] = ["raw_prices"]  # missing db: prefix
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "frontmatter.data_sources" in rules


def test_bad_code_version():
    fm = _base_fm()
    fm["code_version"] = "xyz"  # not 7-char hex
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "frontmatter.code_version" in rules


def test_unknown_ticker_fails():
    fm = _base_fm()
    fm["ticker"] = "ZZZNOTREAL"
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    rules = [f.rule for f in result.failures]
    assert "frontmatter.universe" in rules


def test_known_ticker_passes():
    fm = _base_fm()
    fm["ticker"] = "NVDA"
    result = run_pass1(FAKE_SIGNAL, fm, "signal", TODAY, UNIVERSE)
    assert not any(f.rule == "frontmatter.universe" for f in result.failures)
