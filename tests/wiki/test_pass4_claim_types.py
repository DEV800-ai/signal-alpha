"""Tests for Pass 4 — Claim types."""
from __future__ import annotations

import pytest

from signalalpha.wiki.claim_types import run_pass4


def _signal_body(why_it_works: str = "Volume spikes indicate new information.") -> str:
    return f"""\
## Definition

<!-- claim_type: factual_claim -->

Event: a (ticker, date) where volume spikes.

## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #2](signal_run:2) — 2026-05-05

- N events: 10

<!-- AUTOGEN:END validation_summary -->

## Why it might work

<!-- claim_type: interpretation -->

{why_it_works}

## Known limitations

<!-- claim_type: risk_note -->

- Test fixture.

## Comparable signals

<!-- claim_type: factual_claim -->

- No comparables.

## When to use / when NOT to use

<!-- claim_type: interpretation -->

- USE when: testing.

## Decision history

<!-- claim_type: factual_claim -->

- 2026-05-05 — created. [run_id=2](signal_run:2).
"""


def test_valid_signal_body_passes():
    result = run_pass4(_signal_body(), "signal")
    assert not result.failures


def test_signal_summary_without_signal_run_fails():
    body = """\
## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

No run citation here, just text.

<!-- AUTOGEN:END validation_summary -->
"""
    result = run_pass4(body, "signal")
    rules = [f.rule for f in result.failures]
    assert "claim_type.signal_summary" in rules


def test_interpretation_quantitative_warn():
    body = _signal_body("Volume surged by 30% above the 60-day baseline.")
    result = run_pass4(body, "signal")
    rules = [w.rule for w in result.warnings]
    assert "claim_type.interpretation_quantitative" in rules


def test_interpretation_unsourced_warn():
    # "Why it might work" section has no citation URIs → WARN
    result = run_pass4(_signal_body(), "signal")
    rules = [w.rule for w in result.warnings]
    assert "claim_type.interpretation_unsourced" in rules


def test_unknown_claim_type_fails():
    body = """\
## Definition

<!-- claim_type: made_up_type -->

Some content here.
"""
    result = run_pass4(body, "signal")
    rules = [f.rule for f in result.failures]
    assert "claim_type.unknown" in rules


def test_autogen_signal_summary_with_citation_passes():
    body = """\
## Validation summary

<!-- AUTOGEN:BEGIN validation_summary -->
<!-- claim_type: signal_summary -->

[Run #2](signal_run:2) — date

- Stats here.

<!-- AUTOGEN:END validation_summary -->
"""
    result = run_pass4(body, "signal")
    assert not result.failures
