"""End-to-end validator tests against fixture files."""
from __future__ import annotations

from pathlib import Path

import pytest

from signalalpha.wiki.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"


def test_pass_all(db):
    result = validate(FIXTURES / "volume_anomaly_pass.md", db)
    assert result.verdict == "PASS"
    assert not result.failures


def test_missing_citation_fail(db):
    result = validate(FIXTURES / "missing_citation_fail.md", db)
    assert result.verdict == "FAIL"
    rules = [f.rule for f in result.failures]
    assert "citation.resolution" in rules


def test_bad_uri_fail(db):
    result = validate(FIXTURES / "bad_uri_fail.md", db)
    assert result.verdict == "FAIL"
    rules = [f.rule for f in result.failures]
    assert "citation.syntax" in rules


def test_lifecycle_integrity_fail(db):
    result = validate(FIXTURES / "lifecycle_integrity_fail.md", db)
    assert result.verdict == "FAIL"
    rules = [f.rule for f in result.failures]
    assert "lifecycle.integrity" in rules


def test_unsupported_schema_fail(db):
    result = validate(FIXTURES / "unsupported_schema_fail.md", db)
    assert result.verdict == "FAIL"
    rules = [f.rule for f in result.failures]
    assert "schema_version.unsupported" in rules


def test_interpretation_warn(db):
    result = validate(FIXTURES / "interpretation_warn.md", db)
    assert result.verdict == "PASS"
    assert not result.failures
    assert result.warnings  # at least one warning
    # The warning should come from Pass 4
    pass4_warnings = [w for w in result.warnings if w.pass_num == 4]
    assert pass4_warnings


def test_result_shape(db):
    result = validate(FIXTURES / "volume_anomaly_pass.md", db)
    assert result.page.endswith("volume_anomaly_pass.md")
    assert len(result.pass_results) == 4
    assert {p.pass_num for p in result.pass_results} == {1, 2, 3, 4}
