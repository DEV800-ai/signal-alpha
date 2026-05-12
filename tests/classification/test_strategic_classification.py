"""Tests for signalalpha.classification.strategic_classification."""
from __future__ import annotations

import pytest

from signalalpha.classification.strategic_classification import (
    _FORBIDDEN,
    TYPES,
    classify_candidate,
    build_strategic_view,
    _TICKER_TYPE,
    _TICKER_REASON,
)


# ── Ticker override coverage ───────────────────────────────────────────────────

class TestTickerOverrides:
    def test_known_asymmetric(self):
        result = classify_candidate("ASTS", [], {"status": "validated"}, 0.70, "high")
        assert result["type"] == "Asymmetric"

    def test_known_transitional(self):
        result = classify_candidate("INTC", [], {"status": "borderline"}, 0.55, "medium")
        assert result["type"] == "Transitional"

    def test_known_compounder(self):
        result = classify_candidate("LMT", [], {"status": "validated"}, 0.85, "high")
        assert result["type"] == "Compounder"

    def test_nvda_is_compounder(self):
        assert classify_candidate("NVDA", [], None, 0.90, "high")["type"] == "Compounder"

    def test_rklb_is_asymmetric(self):
        assert classify_candidate("RKLB", [], {"status": "validated"}, 0.60, "medium")["type"] == "Asymmetric"

    def test_dell_is_transitional(self):
        assert classify_candidate("DELL", [], {"status": "validated"}, 0.65, "medium")["type"] == "Transitional"

    def test_all_overrides_have_valid_type(self):
        for ticker, t in _TICKER_TYPE.items():
            assert t in TYPES, f"{ticker} has invalid type {t!r}"

    def test_all_overrides_have_reason(self):
        for ticker in _TICKER_TYPE:
            assert ticker in _TICKER_REASON, f"{ticker} has no reason string"
            assert len(_TICKER_REASON[ticker]) > 10

    def test_override_ignores_quality_score(self):
        r1 = classify_candidate("ASTS", [], {"status": "validated"}, 0.20, "low")
        r2 = classify_candidate("ASTS", [], {"status": "validated"}, 0.95, "high")
        assert r1["type"] == r2["type"] == "Asymmetric"


# ── Heuristic fallback ─────────────────────────────────────────────────────────

class TestHeuristic:
    def _call(self, exposure, hq=0.70, opp="medium"):
        return classify_candidate("ZZZZ", exposure, {"status": "validated"}, hq, opp)

    def test_pre_profitability_is_asymmetric(self):
        assert self._call(["Small-cap", "Pre-profitability"])["type"] == "Asymmetric"

    def test_speculative_is_asymmetric(self):
        assert self._call(["Small-cap", "Speculative"])["type"] == "Asymmetric"

    def test_small_high_growth_is_asymmetric(self):
        assert self._call(["Small-cap", "High-growth"])["type"] == "Asymmetric"

    def test_turnaround_is_transitional(self):
        assert self._call(["Large-cap", "Turnaround"])["type"] == "Transitional"

    def test_large_cap_value_with_quality_is_transitional(self):
        assert self._call(["Large-cap", "Value"], hq=0.60)["type"] == "Transitional"

    def test_large_cap_value_low_quality_not_transitional(self):
        result = self._call(["Large-cap", "Value"], hq=0.40)
        assert result["type"] != "Transitional"

    def test_dividend_high_quality_is_compounder(self):
        assert self._call(["Large-cap", "Dividend"], hq=0.70)["type"] == "Compounder"

    def test_dividend_low_quality_not_compounder(self):
        result = self._call(["Large-cap", "Dividend"], hq=0.50)
        assert result["type"] != "Compounder"

    def test_large_cap_high_quality_high_opp_is_compounder(self):
        assert self._call(["Large-cap", "Growth"], hq=0.75, opp="high")["type"] == "Compounder"

    def test_unclassified_is_signal_play(self):
        assert self._call(["Mid-cap", "Cyclical"], hq=0.55, opp="medium")["type"] == "Signal Play"

    def test_returns_non_empty_reason(self):
        for expo in (
            ["Small-cap", "Pre-profitability"],
            ["Large-cap", "Turnaround"],
            ["Large-cap", "Dividend"],
            ["Mid-cap", "Cyclical"],
        ):
            assert len(self._call(expo)["reason"]) > 0


# ── Return shape ───────────────────────────────────────────────────────────────

class TestReturnShape:
    def test_returns_type_and_reason(self):
        result = classify_candidate("NVDA", [], {"status": "validated"}, 0.90, "high")
        assert "type" in result
        assert "reason" in result

    def test_type_is_valid(self):
        for ticker in ("ASTS", "INTC", "LMT", "ZZZZ"):
            result = classify_candidate(ticker, ["Large-cap", "Dividend"],
                                        {"status": "validated"}, 0.75, "high")
            assert result["type"] in TYPES

    def test_no_signal_does_not_crash(self):
        result = classify_candidate("ZZZZ", ["Small-cap"], None, 0.40, "low")
        assert result["type"] in TYPES

    def test_no_forbidden_words_in_reason(self):
        tickers = list(_TICKER_TYPE.keys()) + ["ZZZZ"]
        for ticker in tickers:
            result = classify_candidate(
                ticker, ["Large-cap", "Dividend", "Value"],
                {"status": "validated"}, 0.75, "medium"
            )
            lower = result["reason"].lower()
            for w in _FORBIDDEN:
                assert w not in lower, f"Forbidden word '{w}' in reason for {ticker}"


# ── build_strategic_view ───────────────────────────────────────────────────────

class TestBuildStrategicView:
    def _candidate(self, ticker, stype):
        return {
            "ticker": ticker, "name": ticker, "sector": "ai_infra",
            "type": stype, "reason": "test reason",
            "role": "Growth", "risk_bucket": "Medium",
            "conviction_level": "Medium", "conviction_reason": "test",
            "themes": ["AI/ML"], "summary": "test summary",
        }

    def test_groups_by_type(self):
        cands = [
            self._candidate("ASTS", "Asymmetric"),
            self._candidate("INTC", "Transitional"),
            self._candidate("LMT",  "Compounder"),
            self._candidate("X",    "Signal Play"),
        ]
        result = build_strategic_view(cands)
        assert result["asymmetric"][0]["ticker"] == "ASTS"
        assert result["transitional"][0]["ticker"] == "INTC"
        assert result["compounder"][0]["ticker"] == "LMT"
        assert result["signal_play"][0]["ticker"] == "X"

    def test_totals_match(self):
        cands = [self._candidate("A", "Asymmetric")] * 3 + [self._candidate("C", "Compounder")] * 2
        result = build_strategic_view(cands)
        assert result["totals"]["asymmetric"] == 3
        assert result["totals"]["compounder"] == 2
        assert result["totals"]["transitional"] == 0
        assert result["totals"]["signal_play"] == 0

    def test_empty_input(self):
        result = build_strategic_view([])
        assert result["totals"] == {"asymmetric": 0, "transitional": 0, "compounder": 0, "signal_play": 0}

    def test_unknown_type_falls_to_signal_play(self):
        cands = [self._candidate("X", "UnknownType")]
        result = build_strategic_view(cands)
        assert result["totals"]["signal_play"] == 1

    def test_returns_all_keys(self):
        result = build_strategic_view([])
        assert {"asymmetric", "transitional", "compounder", "signal_play", "totals"} <= set(result)
