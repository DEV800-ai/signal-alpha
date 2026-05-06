"""Tests for Pass 3 — Citations."""
from __future__ import annotations

import pytest

from signalalpha.wiki.citations import run_pass3


def test_valid_signal_run_citation_passes(db):
    body = "See [Run #2](signal_run:2) for details."
    result = run_pass3(body, db)
    assert not result.failures


def test_missing_signal_run_fails(db):
    body = "See [Run #9999](signal_run:9999) for details."
    result = run_pass3(body, db)
    rules = [f.rule for f in result.failures]
    assert "citation.resolution" in rules


def test_bad_uri_syntax_fails(db):
    body = "See [bad filing](filing:NOT-VALID) for details."
    result = run_pass3(body, db)
    rules = [f.rule for f in result.failures]
    assert "citation.syntax" in rules


def test_external_link_skipped(db):
    body = "See [Google](https://google.com) for context."
    result = run_pass3(body, db)
    assert not result.failures


def test_wiki_crosslink_skipped(db):
    body = "See [other signal](../signals/other.md) for context."
    result = run_pass3(body, db)
    assert not result.failures


def test_ambiguous_link_fails(db):
    body = "See [bad](something_unknown) for context."
    result = run_pass3(body, db)
    rules = [f.rule for f in result.failures]
    assert "citation.ambiguous" in rules


def test_no_citations_passes(db):
    body = "No links here at all."
    result = run_pass3(body, db)
    assert not result.failures


def test_bad_earnings_syntax_fails(db):
    body = "See [earnings](earnings:TOOLONGTICKERXYZ:2026-01-01) for details."
    result = run_pass3(body, db)
    rules = [f.rule for f in result.failures]
    assert "citation.syntax" in rules


def test_web_citation_resolved_from_sources(db):
    db.execute(
        "INSERT OR IGNORE INTO sources (source_uri, scheme, canonical_url, published_at) "
        "VALUES ('web:https://example.com/article', 'web', 'https://example.com/article', '2026-01-01')"
    )
    body = "See [article](web:https://example.com/article) for details."
    result = run_pass3(body, db)
    assert not result.failures


def test_unresolved_web_citation_fails(db):
    body = "See [missing](web:https://not-in-sources.example.com/xyz) for details."
    result = run_pass3(body, db)
    rules = [f.rule for f in result.failures]
    assert "citation.resolution" in rules
