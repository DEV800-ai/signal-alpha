"""Tests for signalalpha.opportunity.opportunity_potential.

Uses in-memory DuckDB seeded with price and fundamentals data.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pytest

from signalalpha.opportunity.opportunity_potential import (
    WEIGHTS,
    _UNKNOWN_THRESHOLD,
    evaluate_opportunity_batch,
    evaluate_opportunity_potential,
)

TODAY = dt.date.today()
AS_OF = str(TODAY)


# ── DB fixtures ────────────────────────────────────────────────────────────────

def _base_db(
    close: float = 110.0,
    sma50_val: float = 100.0,
    sma200_val: float = 90.0,
    vol: int = 1_000_000,
    days: int = 420,
    trailing_pe: float | None = None,
    price_to_book: float | None = None,
    eps_growth_yoy: float | None = None,
    revenue_growth: float | None = None,
    market_cap: float | None = None,
) -> duckdb.DuckDBPyConnection:
    db = duckdb.connect()
    db.execute("CREATE TABLE prices (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT)")
    db.execute("""
        CREATE TABLE fundamentals (
            ticker VARCHAR, as_of_date DATE,
            trailing_pe DOUBLE, forward_pe DOUBLE, price_to_book DOUBLE,
            trailing_eps DOUBLE, eps_growth_yoy DOUBLE, eps_growth_quarterly DOUBLE,
            market_cap DOUBLE, revenue_growth DOUBLE,
            fetched_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY (ticker, as_of_date)
        )
    """)
    db.execute("CREATE TABLE universe (ticker VARCHAR PRIMARY KEY, sector VARCHAR, name VARCHAR)")
    db.execute("INSERT INTO universe VALUES ('AAA', 'ai_infra', 'Test Corp')")

    for i in range(days):
        d = TODAY - dt.timedelta(days=i)
        if i == 0:
            cl = close
        elif i < 50:
            cl = sma50_val
        else:
            cl = sma200_val
        db.execute("INSERT INTO prices VALUES ('AAA', ?, ?, ?)", [d, cl, vol])

    if any(v is not None for v in [trailing_pe, price_to_book, eps_growth_yoy, revenue_growth, market_cap]):
        db.execute("""
            INSERT INTO fundamentals VALUES ('AAA', ?, ?, NULL, ?, NULL, ?, NULL, ?, ?, now())
        """, [TODAY, trailing_pe, price_to_book, eps_growth_yoy, market_cap, revenue_growth])

    return db


# ── Structure ──────────────────────────────────────────────────────────────────

class TestResponseStructure:
    def test_top_level_keys(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["ticker"] == "AAA"
        assert "checks" in r
        assert "score" in r
        assert "status" in r
        assert "summary" in r
        assert "as_of_date" in r
        db.close()

    def test_all_check_keys_present(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        expected = {"valuation_room", "growth_support", "technical_extension",
                    "market_cap_asymmetry", "sector_tailwind", "risk_penalty"}
        assert set(r["checks"].keys()) == expected
        db.close()

    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_score_in_range(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert 0.0 <= r["score"] <= 1.0
        db.close()

    def test_batch_returns_all_tickers(self):
        db = _base_db()
        # Add a second ticker
        for i in range(210):
            d = TODAY - dt.timedelta(days=i)
            db.execute("INSERT INTO prices VALUES ('BBB', ?, 50.0, 500000)", [d])
        results = evaluate_opportunity_batch(
            db, ["AAA", "BBB"], {"AAA": "ai_infra", "BBB": "telecom"}, as_of_date=AS_OF
        )
        assert set(results.keys()) == {"AAA", "BBB"}
        db.close()

    def test_batch_empty_returns_empty(self):
        db = _base_db()
        assert evaluate_opportunity_batch(db, [], {}, as_of_date=AS_OF) == {}
        db.close()


# ── Valuation Room ─────────────────────────────────────────────────────────────

class TestValuationRoom:
    def test_unknown_when_no_fundamentals(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "unknown"
        db.close()

    def test_pass_growth_sector_low_pe(self):
        db = _base_db(trailing_pe=40.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "pass"
        db.close()

    def test_warn_growth_sector_high_pe(self):
        db = _base_db(trailing_pe=80.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "warn"
        db.close()

    def test_fail_growth_sector_stretched_pe(self):
        db = _base_db(trailing_pe=150.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "fail"
        db.close()

    def test_pass_value_sector_low_pe(self):
        db = _base_db(trailing_pe=15.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="telecom", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "pass"
        db.close()

    def test_fail_value_sector_stretched_pe(self):
        db = _base_db(trailing_pe=50.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="telecom", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "fail"
        db.close()

    def test_pb_fallback(self):
        db = _base_db(trailing_pe=None, price_to_book=0.7)
        r = evaluate_opportunity_potential(db, "AAA", sector="telecom", as_of_date=AS_OF)
        assert r["checks"]["valuation_room"]["status"] == "pass"
        db.close()


# ── Growth Support ─────────────────────────────────────────────────────────────

class TestGrowthSupport:
    def test_unknown_when_no_fundamentals(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["growth_support"]["status"] == "unknown"
        db.close()

    def test_pass_strong_eps_growth(self):
        db = _base_db(eps_growth_yoy=0.30)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["growth_support"]["status"] == "pass"
        db.close()

    def test_pass_strong_revenue_growth(self):
        db = _base_db(revenue_growth=0.25)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["growth_support"]["status"] == "pass"
        db.close()

    def test_fail_declining_eps(self):
        db = _base_db(eps_growth_yoy=-0.20)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["growth_support"]["status"] == "fail"
        db.close()


# ── Technical Extension ────────────────────────────────────────────────────────

class TestTechnicalExtension:
    def test_pass_when_close_within_sma50(self):
        # close=110, sma50=100 → 10% above → pass
        db = _base_db(close=110.0, sma50_val=100.0, sma200_val=80.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["technical_extension"]["status"] == "pass"
        db.close()

    def test_warn_when_moderately_above_sma50(self):
        # close=130, sma50=100 → 30% above → fail threshold; but 200d is fine
        # Actually >30% is fail for SMA50. Let me use 20% above.
        # close=120, sma50=100 → 20% above → warn
        db = _base_db(close=120.0, sma50_val=100.0, sma200_val=80.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["technical_extension"]["status"] == "warn"
        db.close()

    def test_fail_when_strongly_above_sma50(self):
        # close=140, sma50=100 → 40% above → fail
        db = _base_db(close=140.0, sma50_val=100.0, sma200_val=80.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["technical_extension"]["status"] == "fail"
        db.close()

    def test_unknown_with_short_history(self):
        db = duckdb.connect()
        db.execute("CREATE TABLE prices (ticker VARCHAR, date DATE, close DOUBLE, volume BIGINT)")
        db.execute("CREATE TABLE fundamentals (ticker VARCHAR, as_of_date DATE, trailing_pe DOUBLE, forward_pe DOUBLE, price_to_book DOUBLE, trailing_eps DOUBLE, eps_growth_yoy DOUBLE, eps_growth_quarterly DOUBLE, market_cap DOUBLE, revenue_growth DOUBLE, fetched_at TIMESTAMP DEFAULT now(), PRIMARY KEY (ticker, as_of_date))")
        # Only 10 days of data
        for i in range(10):
            d = TODAY - dt.timedelta(days=i)
            db.execute("INSERT INTO prices VALUES ('AAA', ?, 100.0, 1000000)", [d])
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["technical_extension"]["status"] == "unknown"
        db.close()


# ── Market Cap Asymmetry ───────────────────────────────────────────────────────

class TestMarketCapAsymmetry:
    def test_unknown_when_missing(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_cap_asymmetry"]["status"] == "unknown"
        db.close()

    def test_warn_mega_cap(self):
        db = _base_db(market_cap=500e9)  # $500B
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_cap_asymmetry"]["status"] == "warn"
        db.close()

    def test_pass_mid_cap(self):
        db = _base_db(market_cap=5e9)  # $5B
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_cap_asymmetry"]["status"] == "pass"
        db.close()

    def test_pass_small_cap(self):
        db = _base_db(market_cap=800e6)  # $800M
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["market_cap_asymmetry"]["status"] == "pass"
        db.close()


# ── Sector Tailwind ────────────────────────────────────────────────────────────

class TestSectorTailwind:
    def test_pass_ai_infra(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["checks"]["sector_tailwind"]["status"] == "pass"
        db.close()

    def test_pass_space_defense(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="space_defense", as_of_date=AS_OF)
        assert r["checks"]["sector_tailwind"]["status"] == "pass"
        db.close()

    def test_warn_telecom(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="telecom", as_of_date=AS_OF)
        assert r["checks"]["sector_tailwind"]["status"] == "warn"
        db.close()

    def test_unknown_missing_sector(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector=None, as_of_date=AS_OF)
        assert r["checks"]["sector_tailwind"]["status"] == "unknown"
        db.close()


# ── Risk Penalty ───────────────────────────────────────────────────────────────

class TestRiskPenalty:
    def test_unknown_when_no_hq(self):
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra",
                                          as_of_date=AS_OF, human_quality=None)
        assert r["checks"]["risk_penalty"]["status"] == "unknown"
        db.close()

    def test_pass_when_all_hq_ok(self):
        hq = {"checks": {
            "liquidity": {"status": "pass"},
            "trend": {"status": "pass"},
            "market_alignment": {"status": "pass"},
            "eps_growth": {"status": "pass"},
        }}
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra",
                                          as_of_date=AS_OF, human_quality=hq)
        assert r["checks"]["risk_penalty"]["status"] == "pass"
        db.close()

    def test_warn_single_risk(self):
        hq = {"checks": {
            "liquidity": {"status": "fail"},
            "trend": {"status": "pass"},
            "market_alignment": {"status": "pass"},
            "eps_growth": {"status": "pass"},
        }}
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra",
                                          as_of_date=AS_OF, human_quality=hq)
        assert r["checks"]["risk_penalty"]["status"] == "warn"
        db.close()

    def test_fail_multiple_risks(self):
        hq = {"checks": {
            "liquidity": {"status": "fail"},
            "trend": {"status": "fail"},
            "market_alignment": {"status": "fail"},
            "eps_growth": {"status": "pass"},
        }}
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra",
                                          as_of_date=AS_OF, human_quality=hq)
        assert r["checks"]["risk_penalty"]["status"] == "fail"
        db.close()


# ── Overall Score and Status ────────────────────────────────────────────────────

class TestScoreAndStatus:
    def test_status_unknown_when_too_many_unknowns(self):
        # With no fundamentals, no market_cap, no human_quality, no 12m price data
        # valuation_room=unknown, growth_support=unknown, market_cap_asymmetry=unknown,
        # risk_penalty=unknown → 4 unknowns → status=unknown
        db = _base_db()
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        assert r["status"] == "unknown"
        db.close()

    def test_status_high_with_good_data(self):
        # pass: sector(ai_infra), valuation(pe=30), growth(eps=+30%), market_cap(mid), tech(within range)
        hq = {"checks": {
            "liquidity": {"status": "pass"},
            "trend": {"status": "pass"},
            "market_alignment": {"status": "pass"},
            "eps_growth": {"status": "pass"},
        }}
        db = _base_db(trailing_pe=30.0, eps_growth_yoy=0.30, market_cap=5e9,
                      close=110.0, sma50_val=100.0, sma200_val=80.0)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra",
                                          as_of_date=AS_OF, human_quality=hq)
        assert r["status"] in ("high", "medium")
        assert r["score"] >= 0.45
        db.close()

    def test_no_forbidden_language_in_summary(self):
        forbidden = ("buy", "sell", "hold", "recommend", "target price", "stop loss")
        db = _base_db(trailing_pe=80.0, eps_growth_yoy=0.10)
        r = evaluate_opportunity_potential(db, "AAA", sector="ai_infra", as_of_date=AS_OF)
        text = r["summary"].lower()
        for word in forbidden:
            assert word not in text, f"Forbidden word '{word}' in opportunity summary"
        db.close()
