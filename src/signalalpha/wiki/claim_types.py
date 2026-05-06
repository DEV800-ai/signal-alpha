"""Pass 4 — Claim types: citation-presence and interpretation nuance."""
from __future__ import annotations

import re

from signalalpha.wiki.types import Issue, PassResult

_H2 = re.compile(r"^##\s+(.+)$")
_H3 = re.compile(r"^###\s+")
_CLAIM_TYPE_RE = re.compile(r"^<!--\s*claim_type:\s*(\w+)\s*-->$")
_AUTOGEN_BEGIN = re.compile(r"<!--\s*AUTOGEN:BEGIN\s+\S+\s*-->")
_AUTOGEN_END = re.compile(r"<!--\s*AUTOGEN:END\s+\S+\s*-->")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_SIGNAL_RUN_RE = re.compile(r"\(signal_run:\d+\)")
_QUANTITATIVE_RE = re.compile(r"\d+(\.\d+)?%|p\s*[<=]\s*\d")

KNOWN_SCHEMES = frozenset(
    ["filing", "tx", "earnings", "signal_run", "price", "news", "transcript", "patent", "web"]
)

# ── Section-default claim_types per page type ─────────────────────────────────
SECTION_DEFAULTS: dict[str, dict[str, str]] = {
    "signal": {
        "definition": "factual_claim",
        "validation summary": "signal_summary",
        "why it might work": "interpretation",
        "known limitations": "risk_note",
        "comparable signals": "factual_claim",
        "when to use / when not to use": "interpretation",
        "decision history": "factual_claim",
    },
    "company": {
        "strategic position": "interpretation",
        "bull case": "interpretation",
        "bear case": "risk_note",
        "what is priced in": "interpretation",
        "recent catalysts": "factual_claim",
        "signal history": "signal_summary",
        "watch list": "risk_note",
    },
    "sector": {
        "sector thesis": "interpretation",
        "active themes": "interpretation",
        "constituents": "factual_claim",
        "cross-sector dependencies": "interpretation",
        "sector-level catalysts": "factual_claim",
        "open questions": "interpretation",
    },
}

_LEADING_NUM = re.compile(r"^\d+\.\s+")
_TRAILING_PAREN = re.compile(r"\s*\(.*\)\s*$")


def _normalize_heading(h: str) -> str:
    h = h.strip().lower()
    h = _LEADING_NUM.sub("", h)
    h = _TRAILING_PAREN.sub("", h)
    return h.strip()


def _has_citation_uri(text: str) -> bool:
    """True if text contains at least one citation-scheme URI link."""
    for _, target in _LINK_RE.findall(text):
        base = target.split("#")[0]
        if base.startswith("http://") or base.startswith("https://"):
            continue
        if base.endswith(".md"):
            continue
        if ":" in base and base.split(":")[0] in KNOWN_SCHEMES:
            return True
    return False


def _has_signal_run_citation(text: str) -> bool:
    return bool(_SIGNAL_RUN_RE.search(text))


def _has_any_link(text: str) -> bool:
    return bool(_LINK_RE.search(text))


def _parse_blocks(section_lines: list[str], default_claim_type: str) -> list[tuple[str, str]]:
    """
    Parse section lines into (claim_type, block_text) pairs.
    AUTOGEN-bounded regions are treated as a single logical block.
    """
    blocks: list[tuple[str, str]] = []
    pending_override: str | None = None
    current_lines: list[str] = []
    current_claim_type = default_claim_type

    # AUTOGEN state
    in_autogen = False
    autogen_claim_type = default_claim_type
    autogen_lines: list[str] = []

    for line in section_lines:
        # AUTOGEN begin
        if _AUTOGEN_BEGIN.search(line):
            if current_lines:
                blocks.append((current_claim_type, "\n".join(current_lines)))
                current_lines = []
                current_claim_type = default_claim_type
            in_autogen = True
            autogen_claim_type = pending_override or default_claim_type
            pending_override = None
            autogen_lines = []
            continue

        # AUTOGEN end
        if _AUTOGEN_END.search(line):
            if in_autogen:
                if autogen_lines:
                    blocks.append((autogen_claim_type, "\n".join(autogen_lines)))
                in_autogen = False
                autogen_lines = []
            continue

        if in_autogen:
            m = _CLAIM_TYPE_RE.match(line.strip())
            if m:
                autogen_claim_type = m.group(1)
            else:
                autogen_lines.append(line)
            continue

        # H3 heading resets pending override and current claim_type.
        if _H3.match(line):
            if current_lines:
                blocks.append((current_claim_type, "\n".join(current_lines)))
                current_lines = []
            current_claim_type = default_claim_type
            pending_override = None
            continue

        # Claim-type override comment.
        m = _CLAIM_TYPE_RE.match(line.strip())
        if m:
            pending_override = m.group(1)
            continue

        # Blank line ends a block.
        if not line.strip():
            if current_lines:
                blocks.append((current_claim_type, "\n".join(current_lines)))
                current_lines = []
                current_claim_type = default_claim_type
                if pending_override:
                    current_claim_type = pending_override
                    pending_override = None
            continue

        # Content line: start new block with pending override if applicable.
        if not current_lines and pending_override:
            current_claim_type = pending_override
            pending_override = None
        current_lines.append(line)

    if in_autogen and autogen_lines:
        blocks.append((autogen_claim_type, "\n".join(autogen_lines)))
    if current_lines:
        blocks.append((current_claim_type, "\n".join(current_lines)))

    return blocks


def run_pass4(body: str, page_type: str) -> PassResult:
    failures: list[Issue] = []
    warnings: list[Issue] = []

    section_defaults = SECTION_DEFAULTS.get(page_type, {})
    lines = body.split("\n")

    # ── Split body into H2 sections ───────────────────────────────────────────
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        m = _H2.match(line)
        if m:
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = _normalize_heading(m.group(1))
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, current_lines))

    # ── Validate each section ─────────────────────────────────────────────────
    for section_name, sec_lines in sections:
        default_ct = section_defaults.get(section_name, "factual_claim")
        blocks = _parse_blocks(sec_lines, default_ct)
        section_text = "\n".join(sec_lines)

        for block_ct, block_text in blocks:
            if not block_text.strip():
                continue

            # Validate unknown claim_type values (FAIL).
            valid_types = {"factual_claim", "signal_summary", "private_company_context",
                           "interpretation", "risk_note"}
            if block_ct not in valid_types:
                failures.append(Issue(
                    4, "claim_type.unknown",
                    f"Unknown claim_type '{block_ct}' in section '{section_name}'. "
                    f"Valid types: {sorted(valid_types)}. "
                    f"Resolution: correct the claim_type override comment.",
                    location=f"section '{section_name}'",
                ))
                continue

            if block_ct == "signal_summary":
                # REQUIRED: at least one signal_run:N citation in the block.
                if not _has_signal_run_citation(block_text):
                    failures.append(Issue(
                        4, "claim_type.signal_summary",
                        f"Block with claim_type 'signal_summary' in section '{section_name}' "
                        f"has no signal_run:N citation. "
                        f"Resolution: add a [label](signal_run:N) citation referencing the source run.",
                        location=f"section '{section_name}'",
                    ))

            elif block_ct in ("factual_claim", "private_company_context"):
                # WARN (v1 pragmatic): factual blocks should have at least one link.
                # Blocks with only wiki cross-links or no links at all get a warning.
                if not _has_any_link(block_text):
                    warnings.append(Issue(
                        4, "claim_type.missing_citation",
                        f"Block with claim_type '{block_ct}' in section '{section_name}' "
                        f"has no citations or links. Consider adding a citation.",
                        location=f"section '{section_name}'",
                    ))

            elif block_ct == "interpretation":
                # WARN if block has quantitative assertion without a citation URI.
                if _QUANTITATIVE_RE.search(block_text) and not _has_citation_uri(block_text):
                    warnings.append(Issue(
                        4, "claim_type.interpretation_quantitative",
                        f"Interpretation block in section '{section_name}' contains a quantitative "
                        f"assertion without a citation. "
                        f"Resolution: add a citation or rephrase to remove the specific number.",
                        location=f"section '{section_name}'",
                    ))

        # Interpretation nuance: WARN if entire section has zero citation URIs.
        if default_ct == "interpretation" or all(
            ct == "interpretation" for ct, _ in blocks if _
        ):
            is_interp_section = section_defaults.get(section_name) == "interpretation"
            if is_interp_section and not _has_citation_uri(section_text):
                warnings.append(Issue(
                    4, "claim_type.interpretation_unsourced",
                    f"Interpretation section '{section_name}' contains zero citation URIs. "
                    f"Consider adding at least one citation to ground the interpretation.",
                    location=f"section '{section_name}'",
                ))

    return PassResult(4, tuple(failures), tuple(warnings))
