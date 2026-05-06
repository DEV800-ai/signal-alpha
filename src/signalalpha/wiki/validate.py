"""Public entry point: validate(page_path, db) -> ValidationResult."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import duckdb
import yaml

from signalalpha.wiki.citations import run_pass3
from signalalpha.wiki.claim_types import run_pass4
from signalalpha.wiki.frontmatter import run_pass1
from signalalpha.wiki.structure import run_pass2
from signalalpha.wiki.types import PassResult, ValidationResult

_FM_DELIMITER = re.compile(r"^---\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body; return (fm_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    parts = _FM_DELIMITER.split(text, maxsplit=2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return fm, body


def _detect_page_type(page_path: Path, fm: dict) -> str:
    """Detect page type from path, falling back to frontmatter shape."""
    p = str(page_path).replace("\\", "/")
    if "/wiki/signals/" in p:
        return "signal"
    if "/wiki/companies/" in p:
        return "company"
    if "/wiki/sectors/" in p:
        return "sector"
    # Infer from frontmatter for sample pages / fixtures.
    if "signal_id" in fm:
        return "signal"
    if "sector_id" in fm:
        return "sector"
    if "ticker" in fm or "slug" in fm:
        return "company"
    return "signal"  # safe default for unknown fixtures


def validate(page_path: Path, db: duckdb.DuckDBPyConnection) -> ValidationResult:
    """
    Run all v1 validator passes (1, 2, 3, 4) against page_path.
    All passes run regardless of earlier failures, to give the full picture.
    """
    text = page_path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    page_type = _detect_page_type(page_path, fm)
    today = date.today()

    p1 = run_pass1(page_path, fm, page_type, today)
    p2 = run_pass2(body, page_type)
    p3 = run_pass3(body, db)
    p4 = run_pass4(body, page_type)

    all_passes: tuple[PassResult, ...] = (p1, p2, p3, p4)
    all_failures = tuple(f for p in all_passes for f in p.failures)
    all_warnings = tuple(w for p in all_passes for w in p.warnings)
    verdict = "PASS" if not all_failures else "FAIL"

    return ValidationResult(
        page=str(page_path),
        verdict=verdict,
        pass_results=all_passes,
        failures=all_failures,
        warnings=all_warnings,
    )


if __name__ == "__main__":
    from signalalpha.wiki.cli import main
    main()
