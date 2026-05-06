"""Tests for Pass 2 — Section structure."""
from __future__ import annotations

import pytest

from signalalpha.wiki.structure import run_pass2

_SIGNAL_SECTIONS = "\n".join(
    f"## {h}"
    for h in [
        "Definition",
        "Validation summary",
        "Why it might work",
        "Known limitations",
        "Comparable signals",
        "When to use / when NOT to use",
        "Decision history",
    ]
)


def test_all_signal_sections_present():
    result = run_pass2(_SIGNAL_SECTIONS, "signal")
    assert not result.failures


def test_missing_section_fails():
    body = "\n".join(f"## {h}" for h in ["Definition", "Why it might work"])
    result = run_pass2(body, "signal")
    rules = [f.rule for f in result.failures]
    assert "structure.missing_section" in rules


def test_out_of_order_sections_fail():
    # Put "Decision history" before "Definition"
    body = "\n".join(
        f"## {h}"
        for h in [
            "Decision history",
            "Definition",
            "Validation summary",
            "Why it might work",
            "Known limitations",
            "Comparable signals",
            "When to use / when NOT to use",
        ]
    )
    result = run_pass2(body, "signal")
    assert result.failures  # either missing or out-of-order


def test_autogen_markers_paired():
    body = (
        "## Validation summary\n"
        "<!-- AUTOGEN:BEGIN validation_summary -->\n"
        "content\n"
        "<!-- AUTOGEN:END validation_summary -->\n"
    )
    result = run_pass2(body, "signal")
    assert not any(f.rule == "structure.autogen_marker" for f in result.failures)


def test_autogen_unclosed_fails():
    body = (
        "## Validation summary\n"
        "<!-- AUTOGEN:BEGIN validation_summary -->\n"
        "content\n"
    )
    result = run_pass2(body, "signal")
    rules = [f.rule for f in result.failures]
    assert "structure.autogen_marker" in rules


def test_autogen_unmatched_end_fails():
    body = (
        "## Validation summary\n"
        "<!-- AUTOGEN:END validation_summary -->\n"
    )
    result = run_pass2(body, "signal")
    rules = [f.rule for f in result.failures]
    assert "structure.autogen_marker" in rules


def test_case_insensitive_section_match():
    body = "\n".join(
        f"## {h}"
        for h in [
            "DEFINITION",
            "VALIDATION SUMMARY",
            "WHY IT MIGHT WORK",
            "KNOWN LIMITATIONS",
            "COMPARABLE SIGNALS",
            "WHEN TO USE / WHEN NOT TO USE",
            "DECISION HISTORY",
        ]
    )
    result = run_pass2(body, "signal")
    assert not result.failures
