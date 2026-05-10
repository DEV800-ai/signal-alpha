"""Tests for signalalpha.wiki.research.build_research.

Uses in-memory DuckDB seeded with minimal signal and price data.
No FastAPI server is started — build_research() is called directly.
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

import duckdb
import pytest

from signalalpha.wiki.research import build_research, _FORBIDDEN, _why_here

TODAY = dt.date.today()
AS_OF = str(TODAY)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _base_db() -> duckdb.DuckDBPyConnection:
    """In-memory DB with minimal schema and one validated signal for AAAA."""
    db = duckdb.connect()
    db.execute("""
        CREATE TABLE universe (ticker VARCHAR PRIMARY KEY, sector VARCHAR, name VARCHAR);
        CREATE TABLE prices (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT);
        CREATE TABLE signal_runs (
            run_id INTEGER PRIMARY KEY, signal_name VARCHAR,
            p_value_vs_sector DOUBLE, hold_days INTEGER,
            run_at TIMESTAMP DEFAULT now()
        );
        CREATE TABLE signal_events (
            id INTEGER PRIMARY KEY, run_id INTEGER, ticker VARCHAR,
            event_date DATE, entry_date DATE, exit_date DATE,
            net_return DOUBLE, alpha_sector DOUBLE
        );
        CREATE TABLE fundamentals (
            ticker VARCHAR, as_of_date DATE,
            trailing_pe DOUBLE, forward_pe DOUBLE, price_to_book DOUBLE,
            trailing_eps DOUBLE, eps_growth_yoy DOUBLE, eps_growth_quarterly DOUBLE,
            fetched_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY (ticker, as_of_date)
        );
        CREATE TABLE top10_snapshots (
            snapshot_date DATE, direction TEXT, rank INTEGER, ticker TEXT,
            score DOUBLE, last_signal DATE, n_signals INTEGER, avg_alpha DOUBLE
        );
    """)

    db.execute("INSERT INTO universe VALUES ('AAAA', 'ai_infra', 'Test Corp')")

    # 210 days of price data so quality checks resolve
    for i in range(210):
        d = TODAY - dt.timedelta(days=i)
        cl = 110.0 if i == 0 else (105.0 if i < 50 else 100.0)
        db.execute("INSERT INTO prices VALUES ('AAAA', ?, ?, 1000000)", [d, cl])
    for i in range(210):
        d = TODAY - dt.timedelta(days=i)
        db.execute("INSERT INTO prices VALUES ('SPY',  ?, 500.0, 5000000)", [d])

    # One validated signal run
    db.execute("INSERT INTO signal_runs VALUES (1, 'volume_spike', 0.02, 30, now())")
    for j in range(10):
        db.execute("""
            INSERT INTO signal_events VALUES (
                ?, 1, 'AAAA', ?, ?, ?, ?, ?
            )""", [
            j,
            TODAY - dt.timedelta(days=5 + j * 10),
            TODAY - dt.timedelta(days=4 + j * 10),
            TODAY - dt.timedelta(days=4 + j * 10 - 30),
            0.03 + j * 0.002,
            0.02 + j * 0.001,
        ])

    return db


# ── Structure ──────────────────────────────────────────────────────────────────

class TestResponseStructure:
    def test_top_level_keys(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["ticker"] == "AAAA"
        assert r["candidate_type"] == "Top Research Candidate"
        assert "signal" in r
        assert "human_quality" in r
        assert "context" in r
        assert "history" in r
        assert "next_steps" in r
        db.close()

    def test_human_quality_keys(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        hq = r["human_quality"]
        assert "score" in hq
        assert "checks" in hq
        assert "summary" in hq
        db.close()

    def test_context_keys(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        ctx = r["context"]
        assert "has_company_page" in ctx
        assert "freshness_status" in ctx
        assert "company_page" in ctx
        db.close()

    def test_history_key(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert "recent_appearances" in r["history"]
        db.close()

    def test_next_steps_is_list(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert isinstance(r["next_steps"], list)
        assert len(r["next_steps"]) > 0
        db.close()


# ── Signal section ─────────────────────────────────────────────────────────────

class TestSignalSection:
    def test_signal_present(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["signal"] is not None
        assert r["signal"]["name"] == "volume_spike"
        db.close()

    def test_signal_validated_status(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["signal"]["status"] == "validated"
        db.close()

    def test_signal_none_for_unknown_ticker(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "ZZZZ", Path(tmp))
        assert r["signal"] is None
        db.close()

    def test_signal_p_value_present(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["signal"]["p_value"] is not None
        assert r["signal"]["p_value"] < 0.05
        db.close()


# ── Context section ────────────────────────────────────────────────────────────

class TestContextSection:
    def test_missing_company_page(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["context"]["has_company_page"] is False
        assert r["context"]["freshness_status"] == "missing"
        db.close()

    def test_existing_current_page(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page_dir = root / "companies" / "public"
            page_dir.mkdir(parents=True)
            (page_dir / "AAAA.md").write_text("# AAAA\n")
            r = build_research(db, "AAAA", root)
        assert r["context"]["has_company_page"] is True
        assert r["context"]["freshness_status"] == "current"
        db.close()

    def test_stale_page(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            import os, time
            root = Path(tmp)
            page_dir = root / "companies" / "public"
            page_dir.mkdir(parents=True)
            p = page_dir / "AAAA.md"
            p.write_text("# AAAA\n")
            # Set mtime to 60 days ago
            old_time = time.time() - 60 * 86400
            os.utime(p, (old_time, old_time))
            r = build_research(db, "AAAA", root)
        assert r["context"]["freshness_status"] == "stale"
        db.close()


# ── Fundamentals unknown ───────────────────────────────────────────────────────

class TestFundamentalsUnknown:
    def test_eps_unknown_when_no_fundamentals(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["human_quality"]["checks"]["eps_growth"]["status"] == "unknown"
        db.close()

    def test_valuation_unknown_when_no_fundamentals(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["human_quality"]["checks"]["valuation"]["status"] == "unknown"
        db.close()

    def test_unknown_does_not_zero_quality_score(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["human_quality"]["score"] > 0
        db.close()


# ── Recent appearances ─────────────────────────────────────────────────────────

class TestRecentAppearances:
    def test_empty_when_no_snapshots(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert r["history"]["recent_appearances"] == []
        db.close()

    def test_appearances_returned_when_present(self):
        db = _base_db()
        db.execute(
            "INSERT INTO top10_snapshots VALUES (?, 'long', 2, 'AAAA', 1.5, ?, 10, 0.02)",
            [TODAY - dt.timedelta(days=5), TODAY - dt.timedelta(days=10)],
        )
        db.execute(
            "INSERT INTO top10_snapshots VALUES (?, 'midterm', 4, 'AAAA', 1.0, ?, 10, 0.015)",
            [TODAY - dt.timedelta(days=20), TODAY - dt.timedelta(days=25)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        apps = r["history"]["recent_appearances"]
        assert len(apps) == 2
        assert apps[0]["direction"] == "long"
        assert apps[0]["rank"] == 2
        db.close()


# ── Why Here ──────────────────────────────────────────────────────────────────

class TestWhyHere:
    def test_why_here_key_in_build_research(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        assert "why_here" in r
        why = r["why_here"]
        assert {"signal", "signal_level", "quality", "opportunity", "main_caution"} <= set(why.keys())
        db.close()

    def test_validated_signal_level(self):
        sig = {"status": "validated", "alpha": 0.02, "n_events": 10, "p_value": 0.02}
        why = _why_here(sig, {}, {})
        assert why["signal_level"] == "validated"
        assert "validated" in why["signal"].lower()
        assert "p=0.020" in why["signal"]

    def test_borderline_signal_level(self):
        sig = {"status": "borderline", "alpha": 0.01, "n_events": 5, "p_value": 0.08}
        why = _why_here(sig, {}, {})
        assert why["signal_level"] == "borderline"
        assert "borderline" in why["signal"].lower()

    def test_none_signal(self):
        why = _why_here(None, {}, {})
        assert why["signal_level"] == "none"
        assert why["signal"]

    def test_quality_all_pass(self):
        hq = {"checks": {
            "liquidity": {"status": "pass", "reason": "ok"},
            "trend": {"status": "pass", "reason": "ok"},
        }}
        why = _why_here(None, hq, {})
        assert "passes all" in why["quality"].lower()

    def test_quality_with_fail(self):
        hq = {"checks": {
            "liquidity": {"status": "fail", "reason": "Low volume"},
        }}
        why = _why_here(None, hq, {})
        assert "liquidity" in why["quality"].lower()
        assert "Low volume" in why["main_caution"]

    def test_quality_warn_only(self):
        hq = {"checks": {
            "valuation": {"status": "warn", "reason": "P/E elevated"},
        }}
        why = _why_here(None, hq, {})
        assert "caution" in why["quality"].lower()
        assert "valuation" in why["quality"].lower()

    def test_opp_high(self):
        opp = {"status": "high", "checks": {}}
        why = _why_here(None, {}, opp)
        assert "strong" in why["opportunity"].lower()

    def test_opp_low_with_fails(self):
        opp = {"status": "low", "checks": {
            "valuation_room": {"status": "fail", "reason": "overvalued"},
            "technical_extension": {"status": "fail", "reason": "extended"},
        }}
        why = _why_here(None, {}, opp)
        assert "limited" in why["opportunity"].lower()
        assert "valuation" in why["opportunity"].lower()

    def test_no_forbidden_language_in_why(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        why = r["why_here"]
        all_text = " ".join(why.values()).lower()
        for word in _FORBIDDEN:
            assert word not in all_text, f"Forbidden word '{word}' found in why_here"
        db.close()


# ── No recommendation language ────────────────────────────────────────────────

class TestNoRecommendationLanguage:
    def test_no_forbidden_words_in_next_steps(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        all_text = " ".join(r["next_steps"]).lower()
        for word in _FORBIDDEN:
            assert word not in all_text, f"Forbidden word '{word}' found in next_steps"
        db.close()

    def test_no_forbidden_words_in_signal_summary(self):
        db = _base_db()
        with tempfile.TemporaryDirectory() as tmp:
            r = build_research(db, "AAAA", Path(tmp))
        if r["signal"] and r["signal"].get("summary"):
            text = r["signal"]["summary"].lower()
            for word in _FORBIDDEN:
                assert word not in text, f"Forbidden word '{word}' in signal summary"
        db.close()
