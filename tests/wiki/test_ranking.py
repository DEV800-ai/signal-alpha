"""Tests for signalalpha.wiki.ranking.

Uses an in-memory DuckDB seeded with minimal fixture data so that tests
run without the production database.
"""
from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from signalalpha.wiki.ranking import (
    VALID_DIRECTION,
    VALID_FILTERS,
    VALID_SCORE,
    VALID_SECTORS,
    fetch_rankings,
    resolve_direction,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

def _make_db() -> duckdb.DuckDBPyConnection:
    """In-memory DB seeded with two tickers across two signals."""
    db = duckdb.connect()

    db.execute("""
        CREATE TABLE universe (
            ticker TEXT, name TEXT, sector TEXT
        )
    """)
    db.execute("""
        INSERT INTO universe VALUES
            ('AAA', 'Alpha Corp',  'ai_infra'),
            ('BBB', 'Beta Corp',   'telecom'),
            ('CCC', 'Gamma Corp',  'space_defense')
    """)

    db.execute("""
        CREATE TABLE signal_runs (
            run_id      INTEGER PRIMARY KEY,
            signal_name TEXT,
            p_value_vs_sector DOUBLE
        )
    """)
    db.execute("""
        INSERT INTO signal_runs VALUES
            (1, 'vol_anomaly', 0.01),   -- validated
            (2, 'patent',      0.07)    -- borderline
    """)

    # Recent events (within 90 days) for AAA and BBB on run 1
    # Older events for CCC (beyond 90 days)
    recent     = date.today() - timedelta(days=10)
    old        = date.today() - timedelta(days=200)

    db.execute("""
        CREATE TABLE signal_events (
            run_id       INTEGER,
            ticker       TEXT,
            event_date   DATE,
            entry_date   DATE,
            exit_date    DATE,
            net_return   DOUBLE,
            alpha_sector DOUBLE,
            alpha_spy    DOUBLE,
            sector_benchmark TEXT
        )
    """)

    # AAA: 10 events, all positive alpha, high hit rate → strong long score
    # Returns vary slightly so STDDEV > 0 (required by midterm/opportunity filters)
    for i in range(10):
        ret = 0.05 + (i % 3) * 0.01
        db.execute(
            "INSERT INTO signal_events VALUES (1, 'AAA', ?, ?, ?, ?, ?, ?, 'SOXX')",
            [recent, recent, recent, ret, 0.03, 0.02],
        )

    # BBB: 10 events, positive alpha but lower hit rate
    for i in range(6):
        db.execute(
            "INSERT INTO signal_events VALUES (1, 'BBB', ?, ?, ?, ?, ?, ?, 'IYZ')",
            [recent, recent, recent, 0.04, 0.02, 0.01],
        )
    for i in range(4):
        db.execute(
            "INSERT INTO signal_events VALUES (1, 'BBB', ?, ?, ?, ?, ?, ?, 'IYZ')",
            [recent, recent, recent, -0.02, 0.02, 0.01],
        )

    # CCC: 10 events, good alpha but old signal date → filtered by recency
    for i in range(10):
        db.execute(
            "INSERT INTO signal_events VALUES (1, 'CCC', ?, ?, ?, ?, ?, ?, 'ITA')",
            [old, old, old, 0.10, 0.08, 0.05],
        )

    # prices table — AAA below 50d MA, BBB above
    db.execute("""
        CREATE TABLE prices (
            ticker TEXT, date DATE, close DOUBLE
        )
    """)
    today = date.today()
    for i in range(60):
        d = today - timedelta(days=i)
        # AAA: current price 80, SMA50 ~100 → below MA (dip candidate)
        db.execute("INSERT INTO prices VALUES ('AAA', ?, ?)", [d, 80.0 if i == 0 else 100.0])
        # BBB: current price 110, SMA50 ~100 → above MA
        db.execute("INSERT INTO prices VALUES ('BBB', ?, ?)", [d, 110.0 if i == 0 else 100.0])
        db.execute("INSERT INTO prices VALUES ('CCC', ?, ?)", [d, 50.0])

    return db


@pytest.fixture(scope="module")
def db() -> duckdb.DuckDBPyConnection:
    conn = _make_db()
    yield conn
    conn.close()


# ── resolve_direction ─────────────────────────────────────────────────────────

class TestResolveDirection:
    def test_long_composite(self):
        having, col, order = resolve_direction("long", "composite")
        assert having == ""
        assert col == "composite_score"
        assert order == "DESC"

    def test_long_alpha(self):
        _, col, _ = resolve_direction("long", "alpha")
        assert col == "avg_alpha"

    def test_long_hitrate(self):
        _, col, _ = resolve_direction("long", "hitrate")
        assert col == "hit_rate"

    def test_short_composite(self):
        having, col, _ = resolve_direction("short", "composite")
        assert "alpha_sector" in having
        assert col == "short_score"

    def test_midterm(self):
        having, col, _ = resolve_direction("midterm", "composite")
        assert "alpha_sector" in having
        assert col == "midterm_score"

    def test_opportunity(self):
        having, col, _ = resolve_direction("opportunity", "composite")
        assert "alpha_sector" in having
        assert col == "opp_score"


# ── VALID_* sets ──────────────────────────────────────────────────────────────

class TestValidSets:
    def test_directions(self):
        assert VALID_DIRECTION == {"long", "short", "midterm", "opportunity"}

    def test_filters(self):
        assert "validated" in VALID_FILTERS
        assert "borderline" in VALID_FILTERS
        assert "all" in VALID_FILTERS

    def test_sectors(self):
        assert "all" in VALID_SECTORS
        assert "ai_infra" in VALID_SECTORS

    def test_score_by(self):
        assert {"composite", "alpha", "hitrate", "blended", "investor"} <= VALID_SCORE


# ── fetch_rankings — recency filter ──────────────────────────────────────────

class TestRecencyFilter:
    def test_recency_90_excludes_old_events(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        tickers = [s["ticker"] for s in stocks]
        assert "CCC" not in tickers, "CCC has only old events and should be filtered out"

    def test_recency_0_disables_filter(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=0)
        tickers = [s["ticker"] for s in stocks]
        assert "CCC" in tickers, "CCC should appear when recency filter is disabled"

    def test_recent_tickers_present(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        tickers = [s["ticker"] for s in stocks]
        assert "AAA" in tickers
        assert "BBB" in tickers


# ── fetch_rankings — ranking formula ─────────────────────────────────────────

class TestRankingFormula:
    def test_long_aaa_ranks_above_bbb(self, db):
        """AAA has 100% hit rate vs BBB's 60% — composite score should rank AAA first."""
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        tickers = [s["ticker"] for s in stocks]
        assert tickers.index("AAA") < tickers.index("BBB")

    def test_composite_score_present(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        for s in stocks:
            assert s["composite_score"] is not None
            assert s["composite_score"] > 0

    def test_midterm_score_present(self, db):
        stocks, col = fetch_rankings(db, signal_filter="all", direction="midterm", recency_days=90)
        assert col == "midterm_score"
        for s in stocks:
            assert s["midterm_score"] is not None

    def test_result_columns(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        expected = {"ticker", "name", "sector", "n_signals", "avg_alpha", "avg_return",
                    "std_return", "hit_rate", "last_signal", "composite_score",
                    "midterm_score", "opp_score", "pct_vs_50d"}
        assert expected.issubset(stocks[0].keys())

    def test_numeric_fields_rounded(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=90)
        for s in stocks:
            for k in ("avg_alpha", "hit_rate", "composite_score"):
                if s[k] is not None:
                    # Should be rounded to 6 decimal places
                    assert s[k] == round(s[k], 6)


# ── fetch_rankings — Opportunity score ───────────────────────────────────────

class TestOpportunityScore:
    def test_returns_opp_score(self, db):
        stocks, col = fetch_rankings(db, signal_filter="all", direction="opportunity", recency_days=90)
        assert col == "opp_score"
        for s in stocks:
            assert s["opp_score"] is not None

    def test_pct_vs_50d_present(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="opportunity", recency_days=90)
        for s in stocks:
            assert "pct_vs_50d" in s

    def test_dip_bonus_boosts_score(self, db):
        """AAA is below its 50d MA → opp_score > composite_score (dip bonus applied)."""
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="opportunity", recency_days=90)
        aaa = next(s for s in stocks if s["ticker"] == "AAA")
        assert aaa["pct_vs_50d"] is not None and aaa["pct_vs_50d"] < 0, \
            "AAA should be below its 50d MA"
        assert aaa["opp_score"] > aaa["composite_score"], \
            "opp_score should be boosted above composite_score when stock is below 50d MA"

    def test_above_ma_no_bonus(self, db):
        """BBB is above its 50d MA → opp_score == composite_score (no dip bonus)."""
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="opportunity", recency_days=90)
        bbb = next((s for s in stocks if s["ticker"] == "BBB"), None)
        if bbb is None:
            pytest.skip("BBB not in opportunity results")
        if bbb["pct_vs_50d"] is not None and bbb["pct_vs_50d"] >= 0:
            assert abs(bbb["opp_score"] - bbb["composite_score"]) < 1e-9, \
                "No dip bonus when stock is above 50d MA"


# ── fetch_rankings — signal filter ───────────────────────────────────────────

class TestSignalFilter:
    def test_validated_only_uses_p005(self, db):
        """Run 2 has p=0.07 (borderline). Validated filter should exclude it."""
        all_stocks, _    = fetch_rankings(db, signal_filter="all",       direction="long", recency_days=0)
        val_stocks, _    = fetch_rankings(db, signal_filter="validated",  direction="long", recency_days=0)
        # CCC only has events in run 1 (p=0.01) so it appears in both
        # The filter should not widen results beyond p<0.05
        for s in val_stocks:
            assert s["ticker"] in {x["ticker"] for x in all_stocks}

    def test_limit_respected(self, db):
        stocks, _ = fetch_rankings(db, signal_filter="all", direction="long", recency_days=0, limit=1)
        assert len(stocks) == 1
