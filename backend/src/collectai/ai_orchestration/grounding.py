"""Post-generation grounding check (E5-S3 AC1-AC3, BRD 4.2 critical-violation
item 2).

Customer-facing AI text may only state currency figures, dates and option
identifiers that a deterministic service actually returned. This module
extracts every such figure from a candidate AI message and blocks the
message if any one of them is absent from `GroundedFacts` -- the facts a
caller (a later story's chat flow) computed from rules-engine/domain-service
output. Blocking is total, not partial: one fabricated figure among several
correct ones still blocks the whole message (AC1's "if any is absent").

Supported figure shapes (deliberately narrow -- this is a fabrication guard,
not a general date/currency parser):
- Currency: `$1,234.56`, `$1234`, or a bare `1234.56` (a decimal point is
  required for a bare number so this never mistakes an id or a bucket count
  for money).
- Dates: ISO `YYYY-MM-DD` only. Other English date phrasings are not
  extracted; a real integration point (a later story) is expected to render
  dates in ISO form before this check runs.
- Option identifiers: an uppercase-letter code followed by a hyphen and an
  alphanumeric suffix, e.g. `OPT-A1` (matches the arrangement/option id
  shapes used elsewhere in the system).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

GROUNDING_VIOLATION_EVENT_TYPE: Final[str] = "GROUNDING_VIOLATION"

_CURRENCY_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*\.\d{1,2}\b")
_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_OPTION_PATTERN = re.compile(r"\b[A-Z]{2,6}-[A-Z0-9]{1,8}\b")


@dataclass(frozen=True, slots=True)
class GroundedFacts:
    """The service-computed facts a message is allowed to state."""

    currency_amounts: frozenset[str]
    dates: frozenset[str]
    option_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class GroundingViolation:
    """One figure found in the text that no service result supports."""

    kind: Literal["CURRENCY", "DATE", "OPTION"]
    value: str


@dataclass(frozen=True, slots=True)
class GroundingCheckResult:
    """The outcome of checking one candidate AI message."""

    is_grounded: bool
    violations: tuple[GroundingViolation, ...]
    final_text: str
    audit_event_type: str | None


def check_grounding(
    ai_text: str, facts: GroundedFacts, *, fallback_template: str
) -> GroundingCheckResult:
    """Check `ai_text` against `facts`; substitute `fallback_template` on
    any violation (AC1, AC2). Returns `ai_text` unchanged when every
    extracted figure matches (AC3)."""
    violations = (
        *_check_currency(ai_text, facts.currency_amounts),
        *_check_dates(ai_text, facts.dates),
        *_check_options(ai_text, facts.option_ids),
    )
    if not violations:
        return GroundingCheckResult(
            is_grounded=True, violations=(), final_text=ai_text, audit_event_type=None
        )
    return GroundingCheckResult(
        is_grounded=False,
        violations=violations,
        final_text=fallback_template,
        audit_event_type=GROUNDING_VIOLATION_EVENT_TYPE,
    )


def _check_currency(text: str, allowed: frozenset[str]) -> tuple[GroundingViolation, ...]:
    violations = []
    for raw_match in _CURRENCY_PATTERN.findall(text):
        normalized = _normalize_currency(raw_match)
        if normalized is not None and normalized not in allowed:
            violations.append(GroundingViolation(kind="CURRENCY", value=normalized))
    return tuple(violations)


def _check_dates(text: str, allowed: frozenset[str]) -> tuple[GroundingViolation, ...]:
    return tuple(
        GroundingViolation(kind="DATE", value=value)
        for value in _DATE_PATTERN.findall(text)
        if value not in allowed
    )


def _check_options(text: str, allowed: frozenset[str]) -> tuple[GroundingViolation, ...]:
    return tuple(
        GroundingViolation(kind="OPTION", value=value)
        for value in _OPTION_PATTERN.findall(text)
        if value not in allowed
    )


def _normalize_currency(raw_match: str) -> str | None:
    """Strip `$`/`,` and quantize to 2dp, e.g. "$1,240.0" -> "1240.00"."""
    cleaned = raw_match.replace("$", "").replace(",", "").strip()
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return format(amount, "f")
