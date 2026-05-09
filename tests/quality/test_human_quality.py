"""Tests for signalalpha.quality.human_quality.

Uses an in-memory DuckDB seeded with price data so tests run without
the production database.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pytest

from signalalpha.quality.human_quality import (
    WEIGHTS,
    evaluate_human_quality,
    evaluate_human_quality_batch,
)

AS_OF = "2026-01-10"
TODAY = dt.date.fromisoformat(AS_OF)


# ── Fixture ────────────────────────────────────────────────────────────────────

def _make_db(
    ticker_vol: float = 1_000_000,
    ticker_close: float = 110.0,
    ticker_sma50_base: float = 105.0,
    ticker_sma200_base: float = 100.0,
    ticker_history_days: int = 210,
    spy_close: float = 500.0,
    spy_sma200_base: float = 480.0,
    etf_close: float = 200.0,
    etf_sma200_base: float = 190.0,
    spy_history_days: int = 210,
) -> duckdb.DuckDBPyConnection:
    db = duckdb.connect()
    db.execute("CREATE TABLE prices (ticker TEXT, date DATE, close DOUBLE, volume BIGINT)")

    def _insert(tkr, close_today, vol, sma_base, days):
        for i in range(days):
            d = TODAY - dt.timedelta(days=i)
            close = close_today if i == 0 else sma_base
            db.execute("INSERT INTO prices VALUES (?, ?, ?, ?)", [tkr, d, close, int(vol)])

    _insert("AAA", ticker_close, ticker_vol, ticker_sma200_base, ticker_history_days)
    # Make 50d base slightly above 200d base to create golden cross
    for i in range(ticker_history_days):
        d = TODAY - dt.timedelta(days=i)
        vol_50 = ticker_vol
        close_50 = ticker_close if i == 0 else (ticker_sma50_base if i < 50 else ticker_sma200_base)
        # Update close for the 50d window to be ticker_sma50_base
        if i < 50:
            db.execute("UPDATE prices SET close = ? WHERE ticker = 'AAA' AND date = ?",
                       [ticker_sma50_base if i > 0 else ticker_close, d])
    _insert("SPY",  spy_close,  1_000_000, spy_sma200_base,  spy_history_days)
    _insert("SOXX", etf_close,  1_000_000, etf_sma200_base,  spy_history_days)

    return db


def _fresh_db() -> duckdb.DuckDBPyConnection:
    """Standard fixture: AAA passes all data-backed checks."""
    db = duckdb.connect()
    db.execute("CREATE TABLE prices (ticker TEXT, date DATE, close DOUBLE, volume BIGINT)")

    def _insert(tkr, close_today, sma50_val, sma200_val, vol, days=210):
        for i in range(days):
            d = TODAY - dt.timedelta(days=i)
            if i == 0:
                cl = close_today
            elif i < 50:
                cl = sma50_val
            else:
                cl = sma200_val
            db.execute("INSERT INTO prices VALUES (?, ?, ?, ?)", [tkr, d, cl, int(vol)])

    # AAA: close(110) > sma50(105) > sma200(100), vol=1M → all pass
    _insert("AAA", 110.0, 105.0, 100.0, 1_000_000)
    # BBB: close(90) < sma200(100) → trend fail, vol=1M
    _insert("BBB", 90.0, 95.0, 100.0, 1_000_000)
    # CCC: close(110) > sma200(100), sma50(95) < sma200(100) → trend warn, vol=300K
    _insert("CCC", 110.0, 95.0, 100.0, 300_000)
    # DDD: low volume → liquidity fail
    _insert("DDD", 110.0, 105.0, 100.0, 100_000)
    # EEE: only 50 days of history → trend unknown
    _insert("EEE", 110.0, 105.0, 100.0, 1_000_000, days=100)  # below _MIN_ROWS_200D=120
    # SPY: above 200d MA → market pass
    _insert("SPY",  500.0, 490.0, 480.0, 5_000_000)
    # SOXX (ai_infra ETF): above 200d MA
    _insert("SOXX", 200.0, 195.0, 190.0, 5_000_000)

    return db


@pytest.fixture(scope="module")
def db() -> duckdb.DuckDBPyConnection:
    conn = _fresh_db()
    yield conn
    conn.close()


# ── Liquidity ──────────────────────────────────────────────────────────────────

class TestLiquidity:
    def test_pass(self, db):
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["liquidity"]["status"] == "pass"
        assert r["checks"]["liquidity"]["score"] == 1.0

    def test_warn(self, db):
        r = evaluate_human_quality(db, "CCC", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["liquidity"]["status"] == "warn"
        assert r["checks"]["liquidity"]["score"] == 0.5

    def test_fail(self, db):
        r = evaluate_human_quality(db, "DDD", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["liquidity"]["status"] == "fail"
        assert r["checks"]["liquidity"]["score"] == 0.0

    def test_unknown_no_ticker(self):
        db2 = duckdb.connect()
        db2.execute("CREATE TABLE prices (ticker TEXT, date DATE, close DOUBLE, volume BIGINT)")
        r = evaluate_human_quality(db2, "ZZZ", as_of_date=AS_OF)
        assert r["checks"]["liquidity"]["status"] == "unknown"
        assert r["checks"]["liquidity"]["score"] == 0.5
        db2.close()


# ── Trend ──────────────────────────────────────────────────────────────────────

class TestTrend:
    def test_pass_uptrend(self, db):
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["trend"]["status"] == "pass"

    def test_fail_downtrend(self, db):
        r = evaluate_human_quality(db, "BBB", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["trend"]["status"] == "fail"
        assert r["checks"]["trend"]["score"] == 0.0

    def test_warn_mixed(self, db):
        r = evaluate_human_quality(db, "CCC", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["trend"]["status"] == "warn"
        assert r["checks"]["trend"]["score"] == 0.5

    def test_unknown_short_history(self, db):
        r = evaluate_human_quality(db, "EEE", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["trend"]["status"] == "unknown"
        assert r["checks"]["trend"]["score"] == 0.5


# ── EPS & Valuation always unknown ────────────────────────────────────────────

class TestFundamentalsAlwaysUnknown:
    def test_eps_unknown(self, db):
        r = evaluate_human_quality(db, "AAA", as_of_date=AS_OF)
        assert r["checks"]["eps_growth"]["status"] == "unknown"
        assert r["checks"]["eps_growth"]["score"] == 0.5

    def test_valuation_unknown(self, db):
        r = evaluate_human_quality(db, "AAA", as_of_date=AS_OF)
        assert r["checks"]["valuation"]["status"] == "unknown"
        assert r["checks"]["valuation"]["score"] == 0.5

    def test_unknown_does_not_block_score(self, db):
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["score"] > 0, "Missing fundamentals should not zero out the score"


# ── Market Alignment ──────────────────────────────────────────────────────────

class TestMarketAlignment:
    def test_pass_both_above(self, db):
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_alignment"]["status"] == "pass"

    def test_unknown_no_benchmark(self):
        db2 = duckdb.connect()
        db2.execute("CREATE TABLE prices (ticker TEXT, date DATE, close DOUBLE, volume BIGINT)")
        for i in range(210):
            d = TODAY - dt.timedelta(days=i)
            db2.execute("INSERT INTO prices VALUES ('AAA', ?, 110.0, 1000000)", [d])
        r = evaluate_human_quality(db2, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_alignment"]["status"] == "unknown"
        db2.close()

    def test_fail_both_below(self):
        db2 = duckdb.connect()
        db2.execute("CREATE TABLE prices (ticker TEXT, date DATE, close DOUBLE, volume BIGINT)")
        for i in range(210):
            d = TODAY - dt.timedelta(days=i)
            # SPY and SOXX: close(80) below sma200(100)
            for tkr in ("AAA", "SPY", "SOXX"):
                cl = 80.0 if i == 0 else 100.0
                db2.execute("INSERT INTO prices VALUES (?, ?, ?, 1000000)", [tkr, d, cl])
        r = evaluate_human_quality(db2, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_alignment"]["status"] == "fail"
        db2.close()


# ── Score calculation ─────────────────────────────────────────────────────────

class TestScoreCalculation:
    def test_score_range(self, db):
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert 0.0 <= r["score"] <= 1.0

    def test_all_pass_max_possible_score(self, db):
        """With EPS+valuation always unknown (0.5), max score < 1.0."""
        r = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        # liq(1.0)*0.25 + trend(1.0)*0.30 + eps(0.5)*0.15 + val(0.5)*0.10 + mkt(1.0)*0.20
        expected = 1.0*0.25 + 1.0*0.30 + 0.5*0.15 + 0.5*0.10 + 1.0*0.20
        assert abs(r["score"] - expected) < 1e-4

    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_score_present_in_result(self, db):
        r = evaluate_human_quality(db, "AAA", as_of_date=AS_OF)
        assert "score" in r
        assert isinstance(r["score"], float)


# ── Batch evaluation ──────────────────────────────────────────────────────────

class TestBatch:
    def test_batch_returns_all_tickers(self, db):
        results = evaluate_human_quality_batch(
            db, ["AAA", "BBB", "CCC"],
            {"AAA": "ai_infra", "BBB": "ai_infra", "CCC": "ai_infra"},
            as_of_date=AS_OF,
        )
        assert set(results.keys()) == {"AAA", "BBB", "CCC"}

    def test_batch_matches_single(self, db):
        single = evaluate_human_quality(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        batch  = evaluate_human_quality_batch(
            db, ["AAA"], {"AAA": "ai_infra"}, as_of_date=AS_OF
        )
        assert batch["AAA"]["score"]  == single["score"]
        assert batch["AAA"]["checks"]["liquidity"]["status"] == \
               single["checks"]["liquidity"]["status"]

    def test_batch_empty_input(self, db):
        assert evaluate_human_quality_batch(db, [], {}, as_of_date=AS_OF) == {}
