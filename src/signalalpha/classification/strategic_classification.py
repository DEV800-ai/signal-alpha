"""Strategic classification layer — Asymmetric / Transitional / Compounder / Signal Play.

Pure Python, no DB access, deterministic from inputs.
No buy/sell/hold/recommend language.
"""
from __future__ import annotations

_FORBIDDEN = ("buy", "sell", "hold", "recommend", "target price", "stop loss")

TYPES = ("Asymmetric", "Transitional", "Compounder", "Signal Play")

# ── Ticker overrides ───────────────────────────────────────────────────────────

_TICKER_TYPE: dict[str, str] = {
    # Asymmetric — small/mid-cap, high uncertainty, high optionality
    "ASTS":  "Asymmetric",
    "RKLB":  "Asymmetric",
    "PL":    "Asymmetric",
    "SPIR":  "Asymmetric",
    "ALAB":  "Asymmetric",
    "AAOI":  "Asymmetric",
    "GSAT":  "Asymmetric",
    "KTOS":  "Asymmetric",
    "SMCI":  "Asymmetric",
    "MRVL":  "Asymmetric",
    "CIEN":  "Asymmetric",
    "COHR":  "Asymmetric",
    "VIAV":  "Asymmetric",
    "LITE":  "Asymmetric",
    # Transitional — changing regime, turnaround, or rerating story
    "INTC":  "Transitional",
    "LUMN":  "Transitional",
    "ERIC":  "Transitional",
    "NOK":   "Transitional",
    "SHEN":  "Transitional",
    "FYBR":  "Transitional",
    "CABO":  "Transitional",
    "USM":   "Transitional",
    "DELL":  "Transitional",
    "HPE":   "Transitional",
    # Compounder — durable recurring value, dividend, stable economics
    "LMT":   "Compounder",
    "RTX":   "Compounder",
    "NOC":   "Compounder",
    "GD":    "Compounder",
    "HII":   "Compounder",
    "BA":    "Compounder",
    "LDOS":  "Compounder",
    "SAIC":  "Compounder",
    "T":     "Compounder",
    "VZ":    "Compounder",
    "TMUS":  "Compounder",
    "AVGO":  "Compounder",
    "QCOM":  "Compounder",
    "CSCO":  "Compounder",
    "IDCC":  "Compounder",
    "IRDM":  "Compounder",
    "NVDA":  "Compounder",
    "AMD":   "Compounder",
    "ANET":  "Compounder",
    "INFN":  "Compounder",
    "CALX":  "Compounder",
}

_TICKER_REASON: dict[str, str] = {
    "ASTS":  "Pre-revenue satellite-to-mobile platform with binary outcome potential.",
    "RKLB":  "Small-cap launch provider with growing optionality on space infrastructure.",
    "PL":    "Satellite imagery platform in an early commercial data market.",
    "SPIR":  "Small-cap satellite analytics with limited revenue and high optionality.",
    "ALAB":  "Optical interconnect specialist riding the AI infrastructure buildout.",
    "AAOI":  "Small-cap optical component supplier benefiting from AI data center demand.",
    "GSAT":  "Satellite connectivity with emerging direct-to-device potential.",
    "KTOS":  "Defense drone and autonomous systems — high growth, high uncertainty.",
    "SMCI":  "AI server infrastructure with volatile earnings and high cyclicality.",
    "MRVL":  "Custom silicon and networking chips — mid-cap with AI infrastructure exposure.",
    "CIEN":  "Optical networking equipment — cyclical mid-cap in the data center upgrade cycle.",
    "COHR":  "Photonics and optical components — cyclical with AI buildout tailwind.",
    "VIAV":  "Optical test and measurement — niche cyclical with modest upside.",
    "LITE":  "Optical components mid-cap levered to data center interconnect demand.",
    "INTC":  "Attempting a structural turnaround in foundry and AI chips from a declining position.",
    "LUMN":  "Fiber infrastructure asset undergoing debt restructuring and strategic reset.",
    "ERIC":  "Telecom equipment vendor recovering from market share losses with improving fundamentals.",
    "NOK":   "Telecom equipment vendor rerating on 5G and private networks recovery.",
    "SHEN":  "Rural broadband operator modernizing infrastructure and revenue model.",
    "FYBR":  "Pure-play fiber buildout story with improving subscriber economics.",
    "CABO":  "Cable operator pivoting to broadband-first model amid cord-cutting pressure.",
    "USM":   "Regional wireless carrier with improving network economics and strategic optionality.",
    "DELL":  "Legacy hardware vendor transitioning to AI infrastructure and enterprise services.",
    "HPE":   "Enterprise IT vendor repositioning toward hybrid cloud and AI workloads.",
    "LMT":   "Defense prime with recurring government contracts and consistent capital return.",
    "RTX":   "Aerospace and defense prime with durable aftermarket and defense backlog.",
    "NOC":   "Defense prime focused on advanced systems with strong government revenue visibility.",
    "GD":    "Diversified defense prime — land systems and Gulfstream provide stable cash flows.",
    "HII":   "Sole-source naval shipbuilder with long-duration government contracts.",
    "BA":    "Aerospace prime recovering production rates with large commercial backlog.",
    "LDOS":  "Defense IT services with long-term government contracts and steady margins.",
    "SAIC":  "Government IT integrator with stable contract backlog and consistent execution.",
    "T":     "Large-cap telecom with stabilizing free cash flow and high dividend yield.",
    "VZ":    "Wireless infrastructure operator with high dividend and stable subscriber economics.",
    "TMUS":  "Wireless market share gainer with improving margins and capital return trajectory.",
    "AVGO":  "Diversified semiconductor and infrastructure software with strong recurring revenue.",
    "QCOM":  "Wireless chip leader with expanding AI edge and automotive revenue streams.",
    "CSCO":  "Enterprise networking and security vendor with durable subscription revenue.",
    "IDCC":  "IP licensing model with durable royalty streams from wireless standards portfolios.",
    "IRDM":  "Satellite IoT connectivity with predictable subscription revenue and low churn.",
    "NVDA":  "AI computing platform with dominant market position and expanding software moat.",
    "AMD":   "Data center and AI chip challenger with growing market share and recurring design wins.",
    "ANET":  "Cloud networking leader with strong customer retention and expanding platform.",
    "INFN":  "Optical networking platform with growing carrier and data center customer base.",
    "CALX":  "Broadband access platform with strong rural carrier adoption and recurring revenue.",
}

# ── Heuristic fallback ─────────────────────────────────────────────────────────

def _classify_by_heuristic(
    exposure: list[str],
    hq_score: float | None,
    opp_status: str | None,
) -> tuple[str, str]:
    score = hq_score or 0.0
    opp   = opp_status or "unknown"
    expo  = " ".join(exposure).lower()

    if any(x in expo for x in ("pre-profitability", "speculative")):
        return "Asymmetric", "Pre-profitability or speculative profile suggests asymmetric upside potential."
    if "small-cap" in expo and "high-growth" in expo:
        return "Asymmetric", "Small-cap high-growth profile with active signal activity."
    if "small-cap" in expo and opp in ("high", "medium"):
        return "Asymmetric", "Small-cap with positive opportunity profile — asymmetric risk/reward."
    if "turnaround" in expo:
        return "Transitional", "Turnaround narrative suggests a regime change in progress."
    if "value" in expo and "large-cap" in expo and score >= 0.55:
        return "Transitional", "Large-cap value with active signal may indicate an early rerating."
    if "dividend" in expo and score >= 0.65:
        return "Compounder", "Dividend-paying large-cap with quality checks supports durable value creation."
    if "large-cap" in expo and score >= 0.70 and opp in ("high", "medium"):
        return "Compounder", "Large-cap with strong quality and opportunity profile."
    return "Signal Play", "Validated signal without a clear strategic category — monitor for thesis development."


# ── Public API ─────────────────────────────────────────────────────────────────

def classify_candidate(
    ticker: str,
    exposure_profile: list[str],
    signal_data: dict | None,
    hq_score: float | None,
    opp_status: str | None,
) -> dict:
    """Classify a single candidate. Returns {type, reason}."""
    if ticker in _TICKER_TYPE:
        return {
            "type":   _TICKER_TYPE[ticker],
            "reason": _TICKER_REASON.get(ticker, ""),
        }
    stype, reason = _classify_by_heuristic(exposure_profile, hq_score, opp_status)
    return {"type": stype, "reason": reason}


def build_strategic_view(candidates: list[dict]) -> dict:
    """Group pre-classified candidates by type.

    Each candidate dict must contain: ticker, name, sector, type, reason,
    role, risk_bucket, conviction_level, conviction_reason, themes, summary.

    Returns {asymmetric, transitional, compounder, signal_play, totals}.
    """
    groups: dict[str, list] = {
        "asymmetric":   [],
        "transitional": [],
        "compounder":   [],
        "signal_play":  [],
    }
    _key = {
        "Asymmetric":   "asymmetric",
        "Transitional": "transitional",
        "Compounder":   "compounder",
        "Signal Play":  "signal_play",
    }
    for c in candidates:
        key = _key.get(c.get("type", "Signal Play"), "signal_play")
        groups[key].append(c)

    return {
        **groups,
        "totals": {k: len(v) for k, v in groups.items()},
    }
