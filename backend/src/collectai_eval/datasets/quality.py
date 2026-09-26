"""Deterministic quality checks for a labelled evaluation dataset (E10-S1 AC5, AC6).

Pure functions over `EvalCase`s: no database, no model, no network. They exist because a MOCK run
proves nothing about labels (the MOCK provider is scripted with each case's own expected answer),
so the checks that *can* be mechanical are done here:

- unique ids, unique normalised messages, messages that differ only by a number or a date, and
  near-duplicates (a similarity threshold over the masked text);
- equivalent messages carrying different labels;
- each case's expected escalation reason against the runner's own deterministic precedence;
- each category's meaning (a DISPUTE case has the DISPUTE label, and so on);
- prohibited sensitive-data patterns;
- the total and per-category counts.

What they cannot do is decide whether a message really means what its label says. That needs a
human reviewer (see `EVAL_DS_V2_LABELLING_RUBRIC.md`).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.persistence.seed.scanner import scan_text_for_dangerous_patterns
from collectai.types.enums import Intent, SpecialRequest, VulnerabilityCategory
from collectai_eval import reporting_rules
from collectai_eval.runner import _predicted_escalation_reason
from collectai_eval.schemas import EvalCase

NEAR_DUPLICATE_THRESHOLD = 0.85
SENSITIVE_CATEGORIES = (
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
    "POLICY_EXCEPTION",
    "POLICY_SETTLEMENT",
    "VULNERABLE_CUSTOMER",
)

_DOCUMENTATION_ONLY_REASONS = frozenset({"AMBIGUOUS_VALIDATION", "UNRESOLVED_UNKNOWN"})
# Categories that are simply "the message has this intent and nothing else".
_INTENT_CATEGORIES = frozenset(
    {
        "PAY_NOW",
        "PROMISE_TO_PAY",
        "PAYMENT_PLAN",
        "FINANCIAL_HARDSHIP",
        "DISPUTE",
        "REQUEST_HUMAN",
        "UNKNOWN",
    }
)
_NON_WORD = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")
_NUMBER_OR_ORDINAL = re.compile(r"\d+(?:st|nd|rd|th)?")
_VARIABLE_WORDS = frozenset(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred thousand first second third fourth fifth "
    "monday tuesday wednesday thursday friday saturday sunday "
    "january february march april may june july august september october november december".split()
)


@dataclass(frozen=True, slots=True)
class QualityFinding:
    check: str
    case_ids: tuple[str, ...]
    detail: str


def normalize_message(message: str) -> str:
    """Lower-case, drop apostrophes and punctuation, collapse whitespace."""
    lowered = message.lower().replace("'", "")
    return _SPACES.sub(" ", _NON_WORD.sub(" ", lowered)).strip()


def mask_variable_parts(normalized: str) -> str:
    """Replace every number, ordinal, number word, weekday and month with `#` (runs collapse), so
    two messages that differ only by an amount or a date compare equal."""
    masked: list[str] = []
    for token in normalized.split():
        is_variable = token in _VARIABLE_WORDS or _NUMBER_OR_ORDINAL.fullmatch(token) is not None
        if is_variable:
            if not masked or masked[-1] != "#":
                masked.append("#")
        else:
            masked.append(token)
    return " ".join(masked)


def _normalized(case: EvalCase) -> str:
    return normalize_message(case.message) or case.message.strip()


def _masked(case: EvalCase) -> str:
    return mask_variable_parts(normalize_message(case.message)) or case.message.strip()


def _groups(cases: Sequence[EvalCase], key: str) -> dict[str, list[EvalCase]]:
    grouped: dict[str, list[EvalCase]] = defaultdict(list)
    for case in cases:
        grouped[_normalized(case) if key == "normalized" else _masked(case)].append(case)
    return {text: members for text, members in grouped.items() if len(members) > 1}


def _ids(members: Sequence[EvalCase]) -> tuple[str, ...]:
    return tuple(case.case_id for case in members)


def _signature(case: EvalCase) -> tuple[object, ...]:
    return (
        case.expected_intent,
        case.expected_vulnerability_detected,
        case.expected_vulnerability_category,
        case.expected_special_request,
        case.expected_escalation_reason,
    )


def check_duplicate_ids(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    seen: dict[str, int] = defaultdict(int)
    for case in cases:
        seen[case.case_id] += 1
    return [
        QualityFinding("duplicate_case_id", (case_id,), f"appears {count} times")
        for case_id, count in seen.items()
        if count > 1
    ]


def check_duplicate_messages(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    return [
        QualityFinding("duplicate_message", _ids(members), f"same normalised text: {text!r}")
        for text, members in _groups(cases, "normalized").items()
    ]


def check_number_or_date_variants(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    """Messages equal once numbers and dates are masked, but not already exact duplicates."""
    exact = {_ids(members) for members in _groups(cases, "normalized").values()}
    return [
        QualityFinding(
            "number_or_date_variant", _ids(members), f"differ only by number/date: {text!r}"
        )
        for text, members in _groups(cases, "masked").items()
        if _ids(members) not in exact
    ]


def check_near_duplicates(
    cases: Sequence[EvalCase], threshold: float = NEAR_DUPLICATE_THRESHOLD
) -> list[QualityFinding]:
    """Pairs whose masked text is at least `threshold` similar (difflib ratio), excluding pairs
    the exact and masked checks already report."""
    already = {
        pair
        for members in (*_groups(cases, "normalized").values(), *_groups(cases, "masked").values())
        for pair in _pairs(_ids(members))
    }
    masked = [(case, _masked(case)) for case in cases]
    findings: list[QualityFinding] = []
    for index, (first, first_text) in enumerate(masked):
        for second, second_text in masked[index + 1 :]:
            if (first.case_id, second.case_id) in already:
                continue
            matcher = SequenceMatcher(None, first_text, second_text)
            if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
                continue
            ratio = matcher.ratio()
            if ratio >= threshold:
                findings.append(
                    QualityFinding(
                        "near_duplicate",
                        (first.case_id, second.case_id),
                        f"similarity {ratio:.2f}: {first.message!r} / {second.message!r}",
                    )
                )
    return findings


def _pairs(ids: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(a, b) for index, a in enumerate(ids) for b in ids[index + 1 :]]


def check_label_conflicts(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    """Equivalent messages (same masked text) whose expected labels differ."""
    return [
        QualityFinding(
            "label_conflict", _ids(members), f"equivalent messages, different labels: {text!r}"
        )
        for text, members in _groups(cases, "masked").items()
        if len({_signature(case) for case in members}) > 1
    ]


def derived_escalation_reason(case: EvalCase) -> str | None:
    """The escalation reason the runner's deterministic precedence yields for this case's own
    expected labels. Raises `ValueError` for an unknown enum value."""
    detected = case.expected_vulnerability_detected
    result = IntentResult(
        label=Intent(case.expected_intent),
        confidence=0.95,
        rationale="quality check",
        vulnerability_detected=detected,
        vulnerability_category=(
            VulnerabilityCategory(case.expected_vulnerability_category)
            if case.expected_vulnerability_category is not None
            else None
        ),
        vulnerability_rationale="quality check" if detected else "",
        special_request=SpecialRequest(case.expected_special_request),
    )
    return _predicted_escalation_reason(result)


def check_escalation_consistency(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    """Each expected escalation reason must equal the deterministic one. Documentation-only reasons
    (state-dependent, not scored by the runner) are allowed only on AMBIGUOUS_VALIDATION cases."""
    findings: list[QualityFinding] = []
    for case in cases:
        expected = case.expected_escalation_reason
        if expected in _DOCUMENTATION_ONLY_REASONS:
            if case.category != "AMBIGUOUS_VALIDATION" or expected != "AMBIGUOUS_VALIDATION":
                findings.append(
                    QualityFinding(
                        "escalation_reason_documentation_only",
                        (case.case_id,),
                        f"{expected!r} is only allowed on AMBIGUOUS_VALIDATION cases",
                    )
                )
            continue
        try:
            derived = derived_escalation_reason(case)
        except ValueError as error:
            findings.append(QualityFinding("invalid_label", (case.case_id,), str(error)[:200]))
            continue
        if derived != expected:
            findings.append(
                QualityFinding(
                    "escalation_reason_mismatch",
                    (case.case_id,),
                    f"expected {expected!r}, deterministic precedence gives {derived!r}",
                )
            )
    return findings


def _category_problem(case: EvalCase) -> str | None:
    intent, category = case.expected_intent, case.category
    special, vulnerable = case.expected_special_request, case.expected_vulnerability_detected
    if (case.expected_vulnerability_category is not None) != vulnerable:
        return "vulnerability_detected and vulnerability_category must be set together"
    if intent == "REQUEST_HUMAN" and (vulnerable or special != "NONE"):
        return "REQUEST_HUMAN must not be combined with a vulnerability signal or special request"
    if category in _INTENT_CATEGORIES:
        if intent != category or vulnerable or special != "NONE":
            return f"a {category} case must have intent {category} and no other signal"
    elif category == "POLICY_SETTLEMENT" and (special != "SETTLEMENT" or vulnerable):
        return "a POLICY_SETTLEMENT case needs special_request SETTLEMENT and no vulnerability"
    elif category == "POLICY_EXCEPTION" and (special != "POLICY_EXCEPTION" or vulnerable):
        return "a POLICY_EXCEPTION case needs special_request POLICY_EXCEPTION, no vulnerability"
    elif category == "VULNERABLE_CUSTOMER" and (not vulnerable or special != "NONE"):
        return "a VULNERABLE_CUSTOMER case needs the vulnerability signal, no special request"
    return None


def check_category_semantics(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    return [
        QualityFinding("category_semantics", (case.case_id,), problem)
        for case in cases
        if (problem := _category_problem(case)) is not None
    ]


def check_prohibited_patterns(cases: Sequence[EvalCase]) -> list[QualityFinding]:
    return [
        QualityFinding("prohibited_pattern", (case.case_id,), "; ".join(found))
        for case in cases
        if (found := scan_text_for_dangerous_patterns(case.message))
    ]


def check_counts(
    cases: Sequence[EvalCase],
    *,
    total: int | None = None,
    per_category: Mapping[str, int] | None = None,
    minimum_categories: Sequence[str] = (),
    minimum: int = reporting_rules.MIN_CASES_FOR_CLAIM,
) -> list[QualityFinding]:
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case.category] += 1
    findings: list[QualityFinding] = []
    if total is not None and len(cases) != total:
        detail = f"expected {total} cases, found {len(cases)}"
        findings.append(QualityFinding("case_count", (), detail))
    if per_category is not None and dict(counts) != dict(per_category):
        detail = f"expected {dict(per_category)}, found {dict(counts)}"
        findings.append(QualityFinding("category_counts", (), detail))
    findings += [
        QualityFinding(
            "category_minimum", (), f"{category} has {counts[category]}, needs {minimum}"
        )
        for category in minimum_categories
        if counts[category] < minimum
    ]
    return findings


def run_all_checks(
    cases: Sequence[EvalCase],
    *,
    total: int | None = None,
    per_category: Mapping[str, int] | None = None,
    minimum_categories: Sequence[str] = (),
) -> list[QualityFinding]:
    return [
        *check_duplicate_ids(cases),
        *check_duplicate_messages(cases),
        *check_number_or_date_variants(cases),
        *check_near_duplicates(cases),
        *check_label_conflicts(cases),
        *check_escalation_consistency(cases),
        *check_category_semantics(cases),
        *check_prohibited_patterns(cases),
        *check_counts(
            cases, total=total, per_category=per_category, minimum_categories=minimum_categories
        ),
    ]
