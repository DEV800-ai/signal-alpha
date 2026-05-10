"""Portfolio context layer — soft heuristics for role, risk, conviction, and exposure.

No buy/sell/hold/recommend language. All decisions are deterministic from input data.
"""
from __future__ import annotations

_FORBIDDEN = ("buy", "sell", "hold", "recommend", "target price", "stop loss")

# ── Theme mappings ─────────────────────────────────────────────────────────────

_SECTOR_THEMES: dict[str, list[str]] = {
    "ai_infra":      ["AI/ML", "Semiconductor", "Data Infrastructure"],
    "space_defense": ["Defense", "Aerospace", "Space"],
    "telecom":       ["Telecom", "Connectivity", "Networks"],
}

_TICKER_THEMES: dict[str, list[str]] = {
    # ai_infra
    "NVDA": ["AI/ML", "Semiconductor", "Data Center"],
    "AMD":  ["AI/ML", "Semiconductor", "Data Center"],
    "INTC": ["Semiconductor", "Data Center", "Turnaround"],
    "AVGO": ["Semiconductor", "Networking", "AI/ML"],
    "MRVL": ["Semiconductor", "Networking", "Data Center"],
    "ALAB": ["AI/ML", "Semiconductor", "Networking"],
    "SMCI": ["AI/ML", "Data Center", "Hardware"],
    "DELL": ["Data Center", "Enterprise IT", "AI/ML"],
    "HPE":  ["Data Center", "Enterprise IT"],
    "ANET": ["Networking", "Data Center", "AI/ML"],
    "CIEN": ["Networking", "Optical"],
    "COHR": ["Optical", "Data Center"],
    "VIAV": ["Optical", "Networking"],
    "LITE": ["Optical", "Networking"],
    "AAOI": ["Optical", "Networking"],
    "ASTS": ["Space", "Satellite", "Telecom"],
    # space_defense
    "LMT":  ["Defense", "Aerospace", "Government Contracts"],
    "RTX":  ["Defense", "Aerospace"],
    "NOC":  ["Defense", "Aerospace"],
    "GD":   ["Defense", "Aerospace"],
    "BA":   ["Aerospace", "Defense"],
    "HII":  ["Defense", "Naval"],
    "LDOS": ["Defense", "IT Services"],
    "SAIC": ["Defense", "IT Services"],
    "KTOS": ["Defense", "Drones"],
    "RKLB": ["Space", "Launch"],
    "PL":   ["Space", "Satellite"],
    "SPIR": ["Space", "Data"],
    "IRDM": ["Satellite", "Telecom"],
    # telecom
    "T":    ["Telecom", "Connectivity", "Dividend"],
    "VZ":   ["Telecom", "Connectivity", "Dividend"],
    "TMUS": ["Telecom", "Wireless", "Growth"],
    "CSCO": ["Networking", "Enterprise IT", "Connectivity"],
    "IDCC": ["IP Licensing", "Wireless", "Patents"],
    "QCOM": ["Semiconductor", "Wireless", "AI/ML"],
    "ERIC": ["Telecom Equipment", "Networks"],
    "NOK":  ["Telecom Equipment", "Networks"],
    "INFN": ["Networking", "Optical"],
    "CALX": ["Broadband", "Networks"],
    "SHEN": ["Telecom", "Rural Broadband"],
    "LUMN": ["Telecom", "Fiber"],
    "FYBR": ["Fiber", "Broadband"],
    "CABO": ["Cable", "Broadband"],
    "USM":  ["Telecom", "Wireless"],
    "GSAT": ["Satellite", "Connectivity"],
}

# ── Exposure mappings ──────────────────────────────────────────────────────────

_SECTOR_EXPOSURE: dict[str, list[str]] = {
    "ai_infra":      ["Technology", "Growth", "Cyclical"],
    "space_defense": ["Defense", "Government", "Dividend"],
    "telecom":       ["Telecom", "Value", "Dividend"],
}

_TICKER_EXPOSURE: dict[str, list[str]] = {
    "NVDA": ["Mega-cap", "High-growth", "AI leader"],
    "AMD":  ["Large-cap", "Cyclical", "AI challenger"],
    "INTC": ["Large-cap", "Turnaround", "Dividend"],
    "AVGO": ["Large-cap", "High-income", "Diversified semis"],
    "MRVL": ["Mid-cap", "Networking exposure"],
    "ALAB": ["Small-cap", "High-growth", "Optical interconnects"],
    "SMCI": ["Mid-cap", "Cyclical", "AI infrastructure"],
    "DELL": ["Large-cap", "Value", "Enterprise IT"],
    "HPE":  ["Large-cap", "Value", "Enterprise IT"],
    "ANET": ["Large-cap", "Growth", "Cloud networking"],
    "CIEN": ["Mid-cap", "Cyclical", "Optical networking"],
    "COHR": ["Large-cap", "Cyclical", "Photonics"],
    "VIAV": ["Mid-cap", "Cyclical", "Test & measurement"],
    "ASTS": ["Small-cap", "Pre-profitability", "Speculative"],
    "RKLB": ["Small-cap", "High-growth", "Speculative"],
    "KTOS": ["Small-cap", "Defense growth"],
    "PL":   ["Small-cap", "Space data"],
    "SPIR": ["Small-cap", "Satellite analytics"],
    "LMT":  ["Large-cap", "Defense prime", "Dividend"],
    "RTX":  ["Large-cap", "Defense prime", "Dividend"],
    "NOC":  ["Large-cap", "Defense prime", "Dividend"],
    "GD":   ["Large-cap", "Defense prime", "Dividend"],
    "T":    ["Large-cap", "High-dividend", "Value"],
    "VZ":   ["Large-cap", "High-dividend", "Value"],
    "TMUS": ["Large-cap", "Wireless growth"],
    "CSCO": ["Large-cap", "Dividend", "Value"],
    "IDCC": ["Small-cap", "IP Royalties", "Non-consensus"],
    "QCOM": ["Large-cap", "Dividend", "Cyclical"],
    "ERIC": ["Mid-cap", "International", "Telecom equipment"],
    "NOK":  ["Mid-cap", "International", "Telecom equipment"],
    "GSAT": ["Small-cap", "Satellite connectivity"],
}


def _get_themes(ticker: str, sector: str) -> list[str]:
    if ticker in _TICKER_THEMES:
        return _TICKER_THEMES[ticker]
    return _SECTOR_THEMES.get(sector, ["Technology"])


def _get_exposure_profile(ticker: str, sector: str) -> list[str]:
    if ticker in _TICKER_EXPOSURE:
        return _TICKER_EXPOSURE[ticker]
    return _SECTOR_EXPOSURE.get(sector, ["Diversified"])


def _get_role(
    signal: dict | None,
    hq_score: float | None,
    opp_status: str | None,
) -> str:
    """Soft heuristic role: Core / Growth / Speculative / Watchlist."""
    sig_status = (signal or {}).get("status", "none")
    score = hq_score or 0.0
    opp = opp_status or "unknown"

    if sig_status == "validated" and score >= 0.75 and opp in ("high", "medium"):
        return "Core"
    if sig_status in ("validated", "borderline") and score >= 0.55:
        return "Growth"
    if signal is not None and score >= 0.35:
        return "Speculative"
    return "Watchlist"


def _get_risk_bucket(
    signal: dict | None,
    hq_score: float | None,
    opp_status: str | None,
) -> str:
    """Soft heuristic risk: Low / Medium / High."""
    sig_status = (signal or {}).get("status", "none")
    score = hq_score or 0.0
    opp = opp_status or "unknown"

    if sig_status == "validated" and score >= 0.75 and opp in ("high", "medium"):
        return "Low"
    if sig_status == "exploratory" or score < 0.4 or opp == "low":
        return "High"
    return "Medium"


def _get_conviction(
    signal: dict | None,
    hq_score: float | None,
    opp_status: str | None,
) -> tuple[str, str]:
    """Soft heuristic conviction level + one-line reason."""
    sig_status = (signal or {}).get("status", "none")
    score = hq_score or 0.0
    opp = opp_status or "unknown"

    if sig_status == "validated" and score >= 0.75 and opp == "high":
        return "High", "Validated signal, strong quality, and high opportunity align."
    if sig_status == "validated" and score >= 0.75 and opp == "medium":
        return "High", "Validated signal and strong quality with medium opportunity."
    if sig_status == "validated" and score >= 0.55:
        return "Medium", "Validated signal with moderate quality checks."
    if sig_status == "borderline" and score >= 0.65 and opp in ("high", "medium"):
        return "Medium", "Borderline signal but quality and opportunity support the thesis."
    if sig_status == "borderline" and score >= 0.55:
        return "Medium", "Borderline signal and adequate quality — use with care."
    if sig_status == "validated":
        return "Low", "Validated signal, but quality or opportunity checks raise concerns."
    return "Low", "Signal is not fully validated or quality checks are limited."


def _build_summary(
    ticker: str,
    role: str,
    risk: str,
    conviction: str,
    themes: list[str],
    signal: dict | None,
) -> str:
    """One-sentence portfolio framing — no recommendation language."""
    sig_status = (signal or {}).get("status", "none")
    theme_str = " / ".join(themes[:2]) if themes else "this sector"

    status_phrase = {
        "validated":   "a validated signal",
        "borderline":  "a borderline signal",
        "exploratory": "an exploratory signal",
        "none":        "no active signal",
    }.get(sig_status, "an exploratory signal")

    role_phrase = {
        "Core":        "a core research candidate",
        "Growth":      "a growth-oriented research candidate",
        "Speculative": "a speculative research candidate",
        "Watchlist":   "a watchlist candidate",
    }.get(role, "a research candidate")

    return (
        f"{ticker} is {role_phrase} in {theme_str} with {status_phrase}, "
        f"{conviction.lower()} conviction, and {risk.lower()} assessed risk."
    )


def build_portfolio_context(
    ticker: str,
    sector: str,
    signal_data: dict | None,
    human_quality: dict,
    opportunity: dict,
) -> dict:
    """Assemble the portfolio context block for a ticker.

    Returns a dict with: role, risk_bucket, conviction, themes,
    exposure_profile, and summary.
    """
    hq_score   = human_quality.get("score")
    opp_status = opportunity.get("status")

    themes   = _get_themes(ticker, sector)
    exposure = _get_exposure_profile(ticker, sector)
    role     = _get_role(signal_data, hq_score, opp_status)
    risk     = _get_risk_bucket(signal_data, hq_score, opp_status)
    conv_level, conv_reason = _get_conviction(signal_data, hq_score, opp_status)
    summary  = _build_summary(ticker, role, risk, conv_level, themes, signal_data)

    return {
        "role":             role,
        "risk_bucket":      risk,
        "conviction":       {"level": conv_level, "reason": conv_reason},
        "themes":           themes,
        "exposure_profile": exposure,
        "summary":          summary,
    }
