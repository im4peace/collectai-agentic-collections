"""Slice 4 closeout: `eval-ds-v2` quality and `eval-ds-v1` integrity. Pure and DB-free.

Two kinds of test live here. The first proves the checked-in v2 dataset passes every deterministic
check in `collectai_eval.datasets.quality`. The second proves each check really *detects* its
problem, on deliberately broken datasets -- a check that can never fail would prove nothing.

None of this proves a label is semantically right: only a human reviewer can (the dataset's
provenance says review is pending), and a MOCK run cannot, because MOCK is scripted with each
case's own expected answer.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace

import pytest

from collectai_eval.datasets import quality
from collectai_eval.datasets._build_eval_ds_v2 import (
    REVIEW_SHEET_PATH,
    build_dataset,
    render_review_sheet,
)
from collectai_eval.datasets.loader import DATASET_V1_PATH, DATASET_V2_PATH, load_dataset
from collectai_eval.schemas import EvalCase

# The approved distribution, written out independently of the builder's own constants.
_APPROVED_COUNTS = {
    "FINANCIAL_HARDSHIP": 30,
    "DISPUTE": 30,
    "REQUEST_HUMAN": 30,
    "POLICY_EXCEPTION": 30,
    "POLICY_SETTLEMENT": 30,
    "VULNERABLE_CUSTOMER": 30,
    "PAY_NOW": 14,
    "PROMISE_TO_PAY": 14,
    "PAYMENT_PLAN": 14,
    "UNKNOWN": 12,
    "EDGE": 12,
    "ADVERSARIAL": 14,
    "AMBIGUOUS_VALIDATION": 4,
}
_SENSITIVE = (
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
    "POLICY_EXCEPTION",
    "POLICY_SETTLEMENT",
    "VULNERABLE_CUSTOMER",
)
# The 13 v1 cases whose escalation reason was null although the deterministic precedence
# yields one. Listed here by hand so the test does not just re-read the builder.
_CORRECTIONS = {
    **{f"ev-{n:03d}": "FINANCIAL_HARDSHIP" for n in range(19, 25)},
    **{f"ev-{n:03d}": "DISPUTE" for n in range(25, 31)},
    "ev-049": "DISPUTE",
}
# eval-ds-v1 as committed at HEAD 515da6f (canonical JSON / LF-normalised builder source).
_V1_JSON_SHA256 = "252cb30f40509105ae0d057879b1cfe8b717dd645a3a3bba410c598197e676d5"
_V1_BUILDER_SHA256 = "96fa7558a9fbf69dc9e08716cfdb30d959a092167ee9edc661a5e62ae09ea586"


def _v1() -> list[EvalCase]:
    return load_dataset(DATASET_V1_PATH).cases


def _v2() -> list[EvalCase]:
    return load_dataset(DATASET_V2_PATH).cases


def _case(
    case_id: str,
    message: str,
    *,
    category: str = "PAY_NOW",
    intent: str = "PAY_NOW",
    vulnerability: str | None = None,
    special: str = "NONE",
    reason: str | None = None,
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        category=category,
        message=message,
        expected_intent=intent,
        expected_vulnerability_detected=vulnerability is not None,
        expected_vulnerability_category=vulnerability,
        expected_special_request=special,
        expected_escalation_reason=reason,
    )


def _promise(case_id: str, message: str, intent: str = "PROMISE_TO_PAY") -> EvalCase:
    return _case(case_id, message, category="PROMISE_TO_PAY", intent=intent)


def _checks(cases: Sequence[EvalCase]) -> set[str]:
    return {finding.check for finding in quality.run_all_checks(cases)}


# --- the checked-in v2 dataset -----------------------------------------------------------------


def test_v2_identity_count_and_sequential_unique_ids() -> None:
    dataset = load_dataset(DATASET_V2_PATH)

    assert dataset.dataset_version == "eval-ds-v2"
    assert len(dataset.cases) == 264
    assert [case.case_id for case in dataset.cases] == [f"ev-{n:03d}" for n in range(1, 265)]


def test_v2_distribution_is_exactly_the_approved_one_and_sensitive_categories_reach_30() -> None:
    counts = Counter(case.category for case in _v2())

    assert dict(counts) == _APPROVED_COUNTS
    assert sum(counts.values()) == 264
    for category in _SENSITIVE:
        assert counts[category] >= 30, category


def test_v2_passes_every_deterministic_quality_check() -> None:
    findings = quality.run_all_checks(
        _v2(), total=264, per_category=_APPROVED_COUNTS, minimum_categories=_SENSITIVE
    )

    assert findings == [], [f"{f.check} {f.case_ids}: {f.detail}" for f in findings]


@pytest.mark.parametrize(
    "check",
    [
        quality.check_duplicate_ids,
        quality.check_duplicate_messages,
        quality.check_number_or_date_variants,
        quality.check_near_duplicates,
        quality.check_label_conflicts,
        quality.check_escalation_consistency,
        quality.check_category_semantics,
        quality.check_prohibited_patterns,
    ],
)
def test_v2_each_check_reports_nothing(check: Callable[[Sequence[EvalCase]], list[object]]) -> None:
    assert check(_v2()) == []


def test_v2_contains_no_llm_call_or_secret_material() -> None:
    text = DATASET_V2_PATH.read_text(encoding="utf-8")

    assert not re.search(r"sk-ant|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY", text, re.IGNORECASE)


# --- v1 integrity and the v1 -> v2 relationship ------------------------------------------------


def test_v1_is_present_and_unchanged() -> None:
    canonical = json.dumps(
        json.loads(DATASET_V1_PATH.read_text(encoding="utf-8")),
        sort_keys=True,
        separators=(",", ":"),
    )
    builder = (DATASET_V1_PATH.parent / "_build_eval_ds_v1.py").read_bytes().replace(b"\r\n", b"\n")

    assert hashlib.sha256(canonical.encode()).hexdigest() == _V1_JSON_SHA256
    assert hashlib.sha256(builder).hexdigest() == _V1_BUILDER_SHA256
    dataset = load_dataset(DATASET_V1_PATH)
    assert dataset.dataset_version == "eval-ds-v1"
    assert len(dataset.cases) == 60


def test_v1_has_exactly_the_13_escalation_label_inconsistencies_v2_corrects() -> None:
    flagged = {f.case_ids[0] for f in quality.check_escalation_consistency(_v1())}

    assert flagged == set(_CORRECTIONS)
    assert len(flagged) == 13
    assert {case.expected_escalation_reason for case in _v1() if case.case_id in flagged} == {None}


def test_v2_keeps_every_v1_case_and_changes_only_the_13_documented_reasons() -> None:
    v2_by_id = {case.case_id: case for case in _v2()}

    for original in _v1():
        current = v2_by_id[original.case_id]
        if original.case_id in _CORRECTIONS:
            assert replace(current, expected_escalation_reason=None) == original
            assert current.expected_escalation_reason == _CORRECTIONS[original.case_id]
        else:
            assert current == original


def test_v2_provenance_states_the_v1_relationship_authorship_and_pending_review() -> None:
    provenance = load_dataset(DATASET_V2_PATH).provenance
    v1_provenance = load_dataset(DATASET_V1_PATH).provenance

    assert provenance["parent_version"] == "eval-ds-v1"
    assert provenance["synthetic_statement"] == v1_provenance["synthetic_statement"]
    assert "AI-assisted" in provenance["authorship_method"]
    assert "Claude" in provenance["authorship_method"]
    assert "unchanged" in provenance["change_summary"]
    assert "eval-ds-v1" in provenance["change_summary"]
    for case_id in _CORRECTIONS:
        assert case_id in provenance["label_corrections"], case_id
    assert provenance["human_review_status"].startswith("NOT REVIEWED - PENDING")
    assert "POLICY_SETTLEMENT" in provenance["known_limitations"]
    assert "EVAL_DS_V2_LABELLING_RUBRIC.md" in provenance["labelling_rubric"]
    # No human has reviewed anything yet, so nobody is recorded as a reviewer.
    assert not {"reviewer", "reviewed_by", "reviewed_on", "review_date"} & set(provenance)


def test_the_checked_in_v2_files_are_exactly_what_the_builder_produces() -> None:
    built = build_dataset()

    assert json.loads(DATASET_V2_PATH.read_text(encoding="utf-8")) == built
    sheet = REVIEW_SHEET_PATH.read_text(encoding="utf-8")
    assert sheet.replace("\r\n", "\n") == render_review_sheet(built)


# --- the human-review sheet --------------------------------------------------------------------


def test_review_sheet_lists_every_sensitive_case_a_sample_of_the_rest_and_no_reviewer() -> None:
    sheet = REVIEW_SHEET_PATH.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (ev-\d{3}) \|", sheet, re.MULTILINE)
    by_id = {case.case_id: case for case in _v2()}

    assert "**Status: NOT REVIEWED - PENDING.**" in sheet
    assert re.search(r"^Reviewer: _+\s+Date: _+\s*$", sheet, re.MULTILINE)
    assert len(rows) == len(set(rows))
    sensitive_ids = {c.case_id for c in _v2() if c.category in _SENSITIVE}
    assert len(sensitive_ids) == 180
    assert sensitive_ids <= set(rows)
    sampled = set(rows) - sensitive_ids
    assert 0 < len(sampled) < 84
    others = set(_APPROVED_COUNTS) - set(_SENSITIVE)
    assert {by_id[case_id].category for case_id in sampled} == others
    case_rows = [line for line in sheet.splitlines() if re.match(r"\| ev-\d{3} \|", line)]
    assert case_rows and all(line.endswith("| | |") for line in case_rows), "verdicts must be blank"


# --- each check must actually detect its problem -----------------------------------------------


def test_normalisation_and_masking() -> None:
    assert quality.normalize_message("I'll pay 1,500 TODAY!!") == "ill pay 1 500 today"
    assert quality.mask_variable_parts("pay 250 on the 1st of next month") == (
        "pay # on the # of next month"
    )
    assert quality.mask_variable_parts("pay in two weeks on friday") == "pay in # weeks on #"


def test_detects_a_duplicate_case_id() -> None:
    cases = [_case("ev-1", "I want to pay now."), _case("ev-1", "Please take my money today.")]

    assert "duplicate_case_id" in _checks(cases)


def test_detects_a_duplicate_normalised_message() -> None:
    cases = [_case("ev-1", "I want to pay now."), _case("ev-2", "i want to pay NOW!!")]

    assert "duplicate_message" in _checks(cases)


def test_detects_messages_that_differ_only_by_a_number_or_a_date() -> None:
    cases = [
        _promise("ev-1", "I will pay 200 on Monday."),
        _promise("ev-2", "I will pay 350 on Friday."),
    ]

    checks = _checks(cases)
    assert "number_or_date_variant" in checks
    assert "duplicate_message" not in checks  # reported by the more specific check, not twice


def test_detects_a_near_duplicate() -> None:
    cases = [
        _case("ev-1", "Could you connect me with a member of your staff please"),
        _case("ev-2", "Could you connect me with a member of your team please"),
    ]

    assert "near_duplicate" in _checks(cases)


def test_a_clearly_different_message_is_not_a_near_duplicate() -> None:
    cases = [
        _case("ev-1", "I want to pay the overdue amount right now."),
        _case("ev-2", "Set up a structured repayment plan for me please.", intent="PAYMENT_PLAN"),
    ]

    assert quality.check_near_duplicates(cases) == []


def test_detects_conflicting_labels_for_equivalent_messages() -> None:
    cases = [
        _promise("ev-1", "I will pay 200 on Monday."),
        _promise("ev-2", "I will pay 400 on Friday.", intent="PAYMENT_PLAN"),
    ]

    assert "label_conflict" in _checks(cases)


def test_detects_a_missing_hardship_escalation_reason() -> None:
    hardship = _case("ev-1", "I lost my job.", category="FINANCIAL_HARDSHIP",
                     intent="FINANCIAL_HARDSHIP")

    findings = quality.check_escalation_consistency([hardship])

    assert [f.check for f in findings] == ["escalation_reason_mismatch"]
    assert "FINANCIAL_HARDSHIP" in findings[0].detail


def test_detects_an_escalation_reason_where_none_is_derived() -> None:
    plain = _case("ev-1", "I want to pay now.", reason="DISPUTE")

    assert [f.check for f in quality.check_escalation_consistency([plain])] == [
        "escalation_reason_mismatch"
    ]


def test_vulnerability_takes_precedence_in_the_derived_reason() -> None:
    vulnerable = _case(
        "ev-1", "My husband died and I cannot pay.", category="VULNERABLE_CUSTOMER",
        intent="FINANCIAL_HARDSHIP", vulnerability="BEREAVEMENT", reason="VULNERABLE_CUSTOMER",
    )
    wrong = replace(vulnerable, expected_escalation_reason="FINANCIAL_HARDSHIP")

    assert quality.check_escalation_consistency([vulnerable]) == []
    assert [f.check for f in quality.check_escalation_consistency([wrong])] == [
        "escalation_reason_mismatch"
    ]


def test_documentation_only_reasons_are_allowed_only_on_ambiguous_validation_cases() -> None:
    allowed = _case("ev-1", "Pay later maybe.", category="AMBIGUOUS_VALIDATION",
                    intent="PROMISE_TO_PAY", reason="AMBIGUOUS_VALIDATION")
    misplaced = replace(allowed, case_id="ev-2", category="PROMISE_TO_PAY")
    unresolved = replace(allowed, case_id="ev-3", expected_escalation_reason="UNRESOLVED_UNKNOWN")

    assert quality.check_escalation_consistency([allowed]) == []
    assert quality.check_escalation_consistency([misplaced, unresolved])
    assert {f.check for f in quality.check_escalation_consistency([misplaced, unresolved])} == {
        "escalation_reason_documentation_only"
    }


def test_detects_an_unknown_enum_value_as_an_invalid_label() -> None:
    bad = _case("ev-1", "I want to pay now.", intent="NOT_AN_INTENT")

    assert [f.check for f in quality.check_escalation_consistency([bad])] == ["invalid_label"]


@pytest.mark.parametrize(
    "case",
    [
        _case("ev-1", "This is not mine.", category="DISPUTE", intent="PAY_NOW"),
        _case("ev-2", "Settle it.", category="POLICY_SETTLEMENT", special="NONE"),
        _case("ev-3", "Bend it.", category="POLICY_EXCEPTION", special="NONE"),
        _case("ev-4", "I am scared.", category="VULNERABLE_CUSTOMER", intent="UNKNOWN"),
        _case("ev-5", "A person please.", category="REQUEST_HUMAN", intent="REQUEST_HUMAN",
              special="SETTLEMENT"),
    ],
)
def test_detects_a_category_whose_labels_contradict_its_meaning(case: EvalCase) -> None:
    assert [f.check for f in quality.check_category_semantics([case])] == ["category_semantics"]


def test_detects_a_prohibited_sensitive_data_pattern() -> None:
    card_shaped_run = "9" * 16  # built at runtime: no card-like digits live in this source file
    cases = [_case("ev-1", f"Please charge {card_shaped_run} for the payment.")]

    assert [f.check for f in quality.check_prohibited_patterns(cases)] == ["prohibited_pattern"]


def test_detects_a_wrong_total_a_wrong_distribution_and_a_short_sensitive_category() -> None:
    cases = [
        _case(f"ev-{n}", f"unique message number {'x' * n}", category="DISPUTE") for n in range(5)
    ]

    findings = quality.check_counts(
        cases, total=264, per_category={"DISPUTE": 30}, minimum_categories=("DISPUTE",)
    )

    assert {f.check for f in findings} == {"case_count", "category_counts", "category_minimum"}
    assert quality.check_counts(cases, total=5, per_category={"DISPUTE": 5}) == []
