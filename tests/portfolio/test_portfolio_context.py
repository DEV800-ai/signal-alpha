"""Tests for signalalpha.portfolio.portfolio_context."""
from __future__ import annotations

import pytest

from signalalpha.portfolio.portfolio_context import (
    _FORBIDDEN,
    _get_themes,
    _get_exposure_profile,
    _get_role,
    _get_risk_bucket,
    _get_conviction,
    _build_summary,
    build_portfolio_context,
)


# ── Theme resolution ───────────────────────────────────────────────────────────

class TestThemes:
    def test_ticker_override_takes_priority(self):
        themes = _get_themes("NVDA", "ai_infra")
        assert "AI/ML" in themes
        assert "Data Center" in themes

    def test_sector_fallback(self):
        themes = _get_themes("UNKNWN", "ai_infra")
        assert themes == ["AI/ML", "Semiconductor", "Data Infrastructure"]

    def test_telecom_sector_default(self):
        themes = _get_themes("UNKNWN", "telecom")
        assert "Telecom" in themes

    def test_space_defense_sector_default(self):
        themes = _get_themes("UNKNWN", "space_defense")
        assert "Defense" in themes

    def test_unknown_sector_returns_list(self):
        themes = _get_themes("UNKNWN", "unknown_sector")
        assert isinstance(themes, list)
        assert len(themes) > 0

    def test_csco_themes(self):
        themes = _get_themes("CSCO", "telecom")
        assert "Networking" in themes

    def test_idcc_themes(self):
        themes = _get_themes("IDCC", "telecom")
        assert "IP Licensing" in themes or "Patents" in themes


# ── Exposure profile ───────────────────────────────────────────────────────────

class TestExposure:
    def test_ticker_override(self):
        expo = _get_exposure_profile("NVDA", "ai_infra")
        assert "Mega-cap" in expo

    def test_sector_fallback(self):
        expo = _get_exposure_profile("UNKNWN", "space_defense")
        assert "Defense" in expo or "Government" in expo

    def test_returns_list(self):
        assert isinstance(_get_exposure_profile("AAA", "ai_infra"), list)


# ── Role determination ─────────────────────────────────────────────────────────

class TestRole:
    def _sig(self, status="validated"):
        return {"status": status}

    def test_core_requires_validated_high_quality_medium_opp(self):
        assert _get_role(self._sig("validated"), 0.80, "medium") == "Core"

    def test_core_requires_validated_high_quality_high_opp(self):
        assert _get_role(self._sig("validated"), 0.90, "high") == "Core"

    def test_validated_low_quality_is_not_core(self):
        role = _get_role(self._sig("validated"), 0.60, "high")
        assert role != "Core"

    def test_validated_good_quality_low_opp_is_growth(self):
        assert _get_role(self._sig("validated"), 0.65, "low") == "Growth"

    def test_borderline_moderate_quality_is_growth(self):
        assert _get_role(self._sig("borderline"), 0.60, "medium") == "Growth"

    def test_exploratory_moderate_quality_is_speculative(self):
        assert _get_role(self._sig("exploratory"), 0.50, "medium") == "Speculative"

    def test_no_signal_is_watchlist(self):
        assert _get_role(None, 0.30, "low") == "Watchlist"

    def test_very_low_quality_with_signal_is_speculative(self):
        assert _get_role(self._sig("validated"), 0.40, "high") == "Speculative"


# ── Risk bucket ────────────────────────────────────────────────────────────────

class TestRiskBucket:
    def _sig(self, status="validated"):
        return {"status": status}

    def test_low_risk_validated_high_quality_medium_opp(self):
        assert _get_risk_bucket(self._sig("validated"), 0.80, "medium") == "Low"

    def test_low_risk_validated_high_quality_high_opp(self):
        assert _get_risk_bucket(self._sig("validated"), 0.85, "high") == "Low"

    def test_high_risk_exploratory_signal(self):
        assert _get_risk_bucket(self._sig("exploratory"), 0.70, "medium") == "High"

    def test_high_risk_low_quality(self):
        assert _get_risk_bucket(self._sig("validated"), 0.30, "high") == "High"

    def test_high_risk_low_opp(self):
        assert _get_risk_bucket(self._sig("validated"), 0.60, "low") == "High"

    def test_medium_risk_borderline(self):
        assert _get_risk_bucket(self._sig("borderline"), 0.65, "medium") == "Medium"

    def test_no_signal_is_medium_or_high(self):
        risk = _get_risk_bucket(None, 0.60, "medium")
        assert risk in ("Medium", "High")


# ── Conviction ─────────────────────────────────────────────────────────────────

class TestConviction:
    def _sig(self, status="validated"):
        return {"status": status}

    def test_high_conviction_validated_strong_quality_high_opp(self):
        level, reason = _get_conviction(self._sig("validated"), 0.85, "high")
        assert level == "High"
        assert reason

    def test_high_conviction_validated_strong_quality_medium_opp(self):
        level, _ = _get_conviction(self._sig("validated"), 0.80, "medium")
        assert level == "High"

    def test_medium_conviction_validated_moderate_quality(self):
        level, _ = _get_conviction(self._sig("validated"), 0.65, "medium")
        assert level == "Medium"

    def test_medium_conviction_borderline_good_quality(self):
        level, _ = _get_conviction(self._sig("borderline"), 0.70, "high")
        assert level == "Medium"

    def test_low_conviction_exploratory(self):
        level, _ = _get_conviction(self._sig("exploratory"), 0.60, "medium")
        assert level == "Low"

    def test_low_conviction_no_signal(self):
        level, _ = _get_conviction(None, 0.50, "medium")
        assert level == "Low"

    def test_reason_is_non_empty(self):
        for status in ("validated", "borderline", "exploratory"):
            _, reason = _get_conviction({"status": status}, 0.70, "medium")
            assert len(reason) > 0


# ── Summary ────────────────────────────────────────────────────────────────────

class TestSummary:
    def test_no_forbidden_words(self):
        summary = _build_summary("NVDA", "Core", "Low", "High",
                                 ["AI/ML", "Semiconductor"], {"status": "validated"})
        lower = summary.lower()
        for w in _FORBIDDEN:
            assert w not in lower, f"Forbidden word '{w}' in summary"

    def test_contains_ticker(self):
        summary = _build_summary("CSCO", "Growth", "Medium", "Medium",
                                 ["Networking"], {"status": "borderline"})
        assert "CSCO" in summary

    def test_contains_role(self):
        summary = _build_summary("T", "Watchlist", "High", "Low",
                                 ["Telecom"], None)
        assert "watchlist" in summary.lower()

    def test_returns_non_empty_string(self):
        summary = _build_summary("X", "Growth", "Medium", "Medium", ["Tech"], None)
        assert isinstance(summary, str)
        assert len(summary) > 10


# ── build_portfolio_context ────────────────────────────────────────────────────

class TestBuildPortfolioContext:
    def _call(self, ticker="NVDA", sector="ai_infra", sig_status="validated",
              hq_score=0.85, opp_status="high"):
        signal = {"status": sig_status, "alpha": 0.02, "n_events": 10} if sig_status else None
        hq = {"score": hq_score, "checks": {}}
        opp = {"status": opp_status, "score": 0.8, "checks": {}}
        return build_portfolio_context(ticker, sector, signal, hq, opp)

    def test_returns_required_keys(self):
        result = self._call()
        assert {"role", "risk_bucket", "conviction", "themes", "exposure_profile", "summary"} <= set(result.keys())

    def test_conviction_is_dict_with_level_and_reason(self):
        result = self._call()
        assert "level" in result["conviction"]
        assert "reason" in result["conviction"]

    def test_themes_is_list(self):
        assert isinstance(self._call()["themes"], list)

    def test_exposure_profile_is_list(self):
        assert isinstance(self._call()["exposure_profile"], list)

    def test_strong_candidate_is_core_low_risk_high_conviction(self):
        result = self._call("NVDA", "ai_infra", "validated", 0.90, "high")
        assert result["role"] == "Core"
        assert result["risk_bucket"] == "Low"
        assert result["conviction"]["level"] == "High"

    def test_weak_candidate_is_watchlist(self):
        result = self._call("X", "ai_infra", sig_status=None, hq_score=0.20, opp_status="low")
        assert result["role"] == "Watchlist"

    def test_summary_no_forbidden_words(self):
        result = self._call()
        lower = result["summary"].lower()
        for w in _FORBIDDEN:
            assert w not in lower, f"Forbidden word '{w}' in summary"

    def test_no_signal_handled_gracefully(self):
        result = self._call(sig_status=None)
        assert result["role"] in ("Core", "Growth", "Speculative", "Watchlist")

    def test_ticker_themes_override_used(self):
        result = self._call("IDCC", "telecom", "validated", 0.70, "medium")
        assert "IP Licensing" in result["themes"] or "Patents" in result["themes"]

    def test_unknown_ticker_uses_sector_default(self):
        result = self._call("ZZZZ", "space_defense", "validated", 0.80, "high")
        assert "Defense" in result["themes"]
