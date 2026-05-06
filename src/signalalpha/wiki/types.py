from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Issue:
    pass_num: int
    rule: str
    message: str
    location: str | None = None


@dataclass(frozen=True)
class PassResult:
    pass_num: int
    failures: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    page: str
    verdict: Literal["PASS", "FAIL"]
    pass_results: tuple[PassResult, ...]
    failures: tuple[Issue, ...]      # flattened across passes
    warnings: tuple[Issue, ...]
