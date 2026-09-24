"""E10-S1 AC1, AC5, AC6: the checked-in dataset itself. Pure, DB-free --
loads `eval_ds_v1.json` straight off disk.
"""

from __future__ import annotations

from collectai_eval.datasets.loader import load_dataset

_REQUIRED_INTENTS = {
    "PAY_NOW",
    "PROMISE_TO_PAY",
    "PAYMENT_PLAN",
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
    "UNKNOWN",
}
_REQUIRED_CATEGORIES = {
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "REQUEST_HUMAN",
    "VULNERABLE_CUSTOMER",
    "ADVERSARIAL",
    "POLICY_SETTLEMENT",
    "POLICY_EXCEPTION",
    "AMBIGUOUS_VALIDATION",
}


def test_ac1_dataset_has_version_provenance_and_at_least_50_cases() -> None:
    dataset = load_dataset()
    assert dataset.dataset_version == "eval-ds-v1"
    assert "authorship_method" in dataset.provenance
    assert "synthetic_statement" in dataset.provenance
    assert "synthetic" in dataset.provenance["synthetic_statement"].lower()
    assert len(dataset.cases) >= 50


def test_ac1_dataset_covers_all_seven_intents() -> None:
    dataset = load_dataset()
    covered = {case.expected_intent for case in dataset.cases}
    missing = _REQUIRED_INTENTS - covered
    assert not missing, f"missing intents: {missing}"


def test_ac5_dataset_covers_every_required_category() -> None:
    dataset = load_dataset()
    covered = {case.category for case in dataset.cases}
    missing = _REQUIRED_CATEGORIES - covered
    assert not missing, f"missing categories: {missing}"


def test_ac5_every_case_carries_intent_safety_and_escalation_fields() -> None:
    dataset = load_dataset()
    for case in dataset.cases:
        assert case.expected_intent
        assert isinstance(case.expected_vulnerability_detected, bool)
        assert case.expected_special_request in {"NONE", "SETTLEMENT", "POLICY_EXCEPTION"}
        # expected_escalation_reason is nullable ("where applicable") -- no
        # further assertion needed beyond the attribute existing, which
        # EvalCase's own dataclass shape already guarantees.


def test_ac5_vulnerable_customer_cases_all_flag_detection_and_a_category() -> None:
    dataset = load_dataset()
    vulnerable_cases = [c for c in dataset.cases if c.category == "VULNERABLE_CUSTOMER"]
    assert len(vulnerable_cases) >= 1
    for case in vulnerable_cases:
        assert case.expected_vulnerability_detected is True
        assert case.expected_vulnerability_category is not None
        assert case.expected_escalation_reason == "VULNERABLE_CUSTOMER"


def test_ac6_case_ids_are_unique() -> None:
    dataset = load_dataset()
    case_ids = [case.case_id for case in dataset.cases]
    assert len(case_ids) == len(set(case_ids))


def test_no_case_message_contains_a_prohibited_pattern() -> None:
    """The dataset is synthetic data too (AC1's provenance statement) --
    reuses the same scanner E9-S4's CI job runs, so a planted card number
    or similar in a future dataset edit fails this test directly, not just
    the separate CI scan."""
    from collectai.persistence.seed.scanner import scan_text_for_dangerous_patterns

    dataset = load_dataset()
    for case in dataset.cases:
        findings = scan_text_for_dangerous_patterns(case.message)
        assert not findings, f"{case.case_id}: {findings}"
