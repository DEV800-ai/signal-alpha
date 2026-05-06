"""Pass 2 — Section structure (minimal v1): required sections present in order + AUTOGEN pairing."""
from __future__ import annotations

import re

from signalalpha.wiki.types import Issue, PassResult

_AUTOGEN_BEGIN = re.compile(r"<!--\s*AUTOGEN:BEGIN\s+(\S+)\s*-->")
_AUTOGEN_END = re.compile(r"<!--\s*AUTOGEN:END\s+(\S+)\s*-->")
_H2 = re.compile(r"^##\s+(.+)$")
_LEADING_NUM = re.compile(r"^\d+\.\s+")
_TRAILING_PAREN = re.compile(r"\s*\(.*\)\s*$")

# Required sections per page type (in order, normalized).
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "signal": [
        "definition",
        "validation summary",
        "why it might work",
        "known limitations",
        "comparable signals",
        "when to use / when not to use",
        "decision history",
    ],
    "company": [
        "strategic position",
        "bull case",
        "bear case",
        "what is priced in",
        "recent catalysts",
        "signal history",
        "watch list",
    ],
    "sector": [
        "sector thesis",
        "active themes",
        "constituents",
        "cross-sector dependencies",
        "sector-level catalysts",
        "open questions",
    ],
}


def _normalize(heading: str) -> str:
    """Lowercase, strip leading number, strip trailing parentheticals."""
    h = heading.strip().lower()
    h = _LEADING_NUM.sub("", h)
    h = _TRAILING_PAREN.sub("", h)
    return h.strip()


def run_pass2(body: str, page_type: str) -> PassResult:
    failures: list[Issue] = []
    warnings: list[Issue] = []

    lines = body.split("\n")

    # ── AUTOGEN marker pairing ────────────────────────────────────────────────
    stack: list[str] = []
    for line in lines:
        m = _AUTOGEN_BEGIN.search(line)
        if m:
            stack.append(m.group(1))
            continue
        m = _AUTOGEN_END.search(line)
        if m:
            name = m.group(1)
            if not stack:
                failures.append(Issue(2, "structure.autogen_marker",
                    f"Unmatched AUTOGEN:END for '{name}' with no open AUTOGEN:BEGIN."))
            elif stack[-1] != name:
                failures.append(Issue(2, "structure.autogen_marker",
                    f"AUTOGEN:END '{name}' does not match open AUTOGEN:BEGIN '{stack[-1]}'."))
                stack.pop()
            else:
                stack.pop()
    for unclosed in stack:
        failures.append(Issue(2, "structure.autogen_marker",
            f"Unclosed AUTOGEN:BEGIN '{unclosed}' — missing matching AUTOGEN:END."))

    # ── Required sections present in order ───────────────────────────────────
    required = REQUIRED_SECTIONS.get(page_type, [])
    if not required:
        return PassResult(2, tuple(failures), tuple(warnings))

    found: list[str] = []
    for line in lines:
        m = _H2.match(line)
        if m:
            found.append(_normalize(m.group(1)))

    # Check each required section is present (in order).
    search_from = 0
    for section in required:
        try:
            idx = found.index(section, search_from)
            search_from = idx + 1
        except ValueError:
            failures.append(Issue(
                2, "structure.missing_section",
                f"Required section '{section}' not found in page (page type: {page_type}). "
                f"Resolution: add the missing section in the correct position.",
                location=f"expected after position {search_from}",
            ))

    # Check ordering: find positions and flag any out-of-order required sections.
    positions = {}
    for section in required:
        try:
            positions[section] = found.index(section)
        except ValueError:
            pass  # already flagged above

    prev_pos = -1
    for section in required:
        pos = positions.get(section)
        if pos is None:
            continue
        if pos < prev_pos:
            failures.append(Issue(
                2, "structure.section_order",
                f"Section '{section}' appears out of order (found at heading index {pos}, "
                f"expected after index {prev_pos}). "
                f"Resolution: reorder sections to match the schema.",
            ))
        prev_pos = pos

    return PassResult(2, tuple(failures), tuple(warnings))
