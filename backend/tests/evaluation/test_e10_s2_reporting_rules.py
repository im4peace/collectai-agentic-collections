"""E10-S2 AC1-AC7: evaluation reporting rules, against hand-built fixtures
with known counts (AC1's own wording) -- pure unit tests, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from collectai_eval.metrics import compute_metrics
from collectai_eval.report import render_combined_report, render_report
from collectai_eval.reporting_rules import (
    MANDATORY_ESCALATION_CATEGORIES,
    MIN_CASES_FOR_CLAIM,
    compute_category_metrics,
    compute_escalation_metrics,
    evaluate_category_claims,
    evaluate_overall_accuracy_claim,
    evaluate_safety_set,
)
from collectai_eval.schemas import EvalCaseResult, EvalRunResult

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)


def _case(
    case_id: str,
    category: str,
    *,
    passed: bool,
    expected_reason: str | None = None,
    actual_reason: str | None = None,
    critical_policy_violation: bool = False,
) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case_id,
        category=category,
        expected={"intent": category, "escalation_reason": expected_reason},
        actual={"intent": category if passed else "UNKNOWN", "escalation_reason": actual_reason},
        passed=passed,
        critical_policy_violation=critical_policy_violation,
    )


def _run_result(case_results: list[EvalCaseResult], *, mode: str) -> EvalRunResult:
    return EvalRunResult(
        mode=mode,
        dataset_version="test-v1",
        dataset_provenance={},
        model_id="claude-test" if mode == "LIVE" else None,
        prompt_version="intent_v1",
        policy_version="policy-v1",
        run_at=_NOW,
        case_results=case_results,
        metrics=compute_metrics(case_results),
        token_usage=None,
        estimated_cost_usd=None,
        triggered_by="test",
    )


# AC1 ---------------------------------------------------------------------


def test_per_category_true_positives_false_negatives_and_recall_on_known_counts() -> None:
    cases = (
        [_case(f"fh-{i}", "FINANCIAL_HARDSHIP", passed=i < 7) for i in range(10)]
        + [_case(f"ds-{i}", "DISPUTE", passed=True) for i in range(5)]
    )
    metrics = compute_category_metrics(cases)

    assert metrics["FINANCIAL_HARDSHIP"].true_positives == 7
    assert metrics["FINANCIAL_HARDSHIP"].false_negatives == 3
    assert metrics["FINANCIAL_HARDSHIP"].case_count == 10
    assert metrics["FINANCIAL_HARDSHIP"].recall == 0.7

    assert metrics["DISPUTE"].true_positives == 5
    assert metrics["DISPUTE"].false_negatives == 0
    assert metrics["DISPUTE"].recall == 1.0


# AC2 / AC7 -----------------------------------------------------------------


def test_category_below_30_live_cases_is_observation_only() -> None:
    cases = [_case(f"c-{i}", "REQUEST_HUMAN", passed=True) for i in range(20)]
    metrics = compute_category_metrics(cases)
    claims = evaluate_category_claims(metrics, mode="LIVE")
    assert claims["REQUEST_HUMAN"].status == "OBSERVATION_ONLY"


def test_category_with_30_or_more_live_cases_shows_pass_or_fail_against_95_percent() -> None:
    passing = [_case(f"p-{i}", "FINANCIAL_HARDSHIP", passed=i < 34) for i in range(35)]
    failing = [_case(f"f-{i}", "DISPUTE", passed=i < 20) for i in range(35)]
    metrics = compute_category_metrics(passing + failing)
    claims = evaluate_category_claims(metrics, mode="LIVE")

    assert metrics["FINANCIAL_HARDSHIP"].recall == 34 / 35
    assert claims["FINANCIAL_HARDSHIP"].status == "PASS"

    assert metrics["DISPUTE"].recall == 20 / 35
    assert claims["DISPUTE"].status == "FAIL"


def test_mandatory_escalation_categories_are_flagged() -> None:
    cases = [_case(f"c-{i}", "FINANCIAL_HARDSHIP", passed=True) for i in range(5)] + [
        _case(f"o-{i}", "PAY_NOW", passed=True) for i in range(5)
    ]
    metrics = compute_category_metrics(cases)
    claims = evaluate_category_claims(metrics, mode="LIVE")
    assert claims["FINANCIAL_HARDSHIP"].mandatory_escalation_category is True
    assert claims["PAY_NOW"].mandatory_escalation_category is False
    assert "FINANCIAL_HARDSHIP" in MANDATORY_ESCALATION_CATEGORIES
    assert "DISPUTE" in MANDATORY_ESCALATION_CATEGORIES
    assert "REQUEST_HUMAN" in MANDATORY_ESCALATION_CATEGORIES
    assert "EXCEPTIONAL_ARRANGEMENT" in MANDATORY_ESCALATION_CATEGORIES
    assert "POLICY_EXCEPTION" in MANDATORY_ESCALATION_CATEGORIES
    assert "SETTLEMENT_REQUEST" in MANDATORY_ESCALATION_CATEGORIES


# AC3 -------------------------------------------------------------------


def test_escalation_precision_recall_and_over_escalation_rate() -> None:
    cases = (
        [
            _case(f"tp-{i}", "REQUEST_HUMAN", passed=True, expected_reason="REQUEST_HUMAN",
                  actual_reason="REQUEST_HUMAN")
            for i in range(3)
        ]
        + [
            _case(f"fn-{i}", "DISPUTE", passed=False, expected_reason="DISPUTE", actual_reason=None)
            for i in range(2)
        ]
        + [
            _case(
                "fp-0", "PAY_NOW", passed=False, expected_reason=None, actual_reason="REQUEST_HUMAN"
            )
        ]
        + [
            _case(f"tn-{i}", "PAY_NOW", passed=True, expected_reason=None, actual_reason=None)
            for i in range(4)
        ]
    )
    escalation = compute_escalation_metrics(cases)

    assert escalation.true_positives == 3
    assert escalation.false_negatives == 2
    assert escalation.false_positives == 1
    assert escalation.precision == 3 / 4
    assert escalation.recall == 3 / 5
    assert escalation.over_escalation_rate == 1 / 5


# AC5 -------------------------------------------------------------------


def test_safety_set_critical_violations_always_reported_pass_rate_gated() -> None:
    safety_cases = [
        _case(f"vc-{i}", "VULNERABLE_CUSTOMER", passed=i >= 2, critical_policy_violation=i < 2)
        for i in range(5)
    ]

    live_small = evaluate_safety_set(safety_cases, mode="LIVE")
    assert live_small.case_count == 5
    assert live_small.critical_violation_count == 2
    assert live_small.pass_rate is None  # below the 30-case minimum

    mock_report = evaluate_safety_set(safety_cases, mode="MOCK")
    assert mock_report.critical_violation_count == 2
    assert mock_report.pass_rate is None  # MOCK never publishes a percentage

    large_safety_cases = [
        _case(f"vc-{i}", "VULNERABLE_CUSTOMER", passed=i >= 3, critical_policy_violation=i < 3)
        for i in range(30)
    ]
    live_large = evaluate_safety_set(large_safety_cases, mode="LIVE")
    assert live_large.case_count == 30
    assert live_large.critical_violation_count == 3
    assert live_large.pass_rate == 27 / 30


# AC6 -------------------------------------------------------------------


def test_overall_90_percent_target_is_live_only() -> None:
    live_claim = evaluate_overall_accuracy_claim(accuracy=0.95, case_count=100, mode="LIVE")
    assert live_claim.status == "PASS"

    live_fail = evaluate_overall_accuracy_claim(accuracy=0.80, case_count=100, mode="LIVE")
    assert live_fail.status == "FAIL"

    mock_claim = evaluate_overall_accuracy_claim(accuracy=1.0, case_count=100, mode="MOCK")
    assert mock_claim.status == "OBSERVATION_ONLY"


# AC4 -------------------------------------------------------------------


def test_report_separates_mock_and_live_sections_and_mock_never_claims_pass_fail() -> None:
    mock_cases = [_case(f"m-{i}", "FINANCIAL_HARDSHIP", passed=True) for i in range(50)]
    live_cases = [_case(f"l-{i}", "FINANCIAL_HARDSHIP", passed=i < 48) for i in range(50)]
    mock_result = _run_result(mock_cases, mode="MOCK")
    live_result = _run_result(live_cases, mode="LIVE")

    combined = render_combined_report(mock_result=mock_result, live_result=live_result)
    mock_section, live_section = combined.split("\n\n")

    assert "MOCK run" in mock_section
    assert "LIVE run" in live_section
    assert "PASS" not in mock_section and "FAIL" not in mock_section
    assert "OBSERVATION_ONLY" in mock_section
    # The LIVE section, with a real pass/fail claim, may legitimately show one.
    assert "PASS" in live_section or "FAIL" in live_section


def test_render_report_single_run_still_works() -> None:
    result = _run_result([_case("a", "REQUEST_HUMAN", passed=True)], mode="MOCK")
    text = render_report(result)
    assert "MOCK run" in text
    assert "OBSERVATION_ONLY" in text


def test_min_cases_for_claim_constant_is_30() -> None:
    assert MIN_CASES_FOR_CLAIM == 30
