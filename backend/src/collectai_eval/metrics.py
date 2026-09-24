"""Aggregate metrics over one run's `EvalCaseResult`s (E10-S1 AC4's own
`eval_run.metrics` JSONB column, and the safety-set signal AC5's
vulnerable-customer cases need): overall accuracy, per-category recall, an
escalation-specific accuracy figure, and the safety-set pass rate.
"""

from __future__ import annotations

from typing import Any

from collectai_eval.schemas import EvalCaseResult

_SAFETY_CATEGORIES = frozenset({"VULNERABLE_CUSTOMER"})


def compute_metrics(case_results: list[EvalCaseResult]) -> dict[str, Any]:
    total = len(case_results)
    passed = sum(1 for r in case_results if r.passed)
    accuracy = passed / total if total else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for result in case_results:
        bucket = by_category.setdefault(result.category, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if result.passed:
            bucket["passed"] += 1
    per_category_recall = {
        category: (counts["passed"] / counts["total"] if counts["total"] else 0.0)
        for category, counts in by_category.items()
    }

    escalation_cases = [r for r in case_results if r.expected.get("escalation_reason") is not None]
    escalation_correct = sum(
        1
        for r in escalation_cases
        if r.actual.get("escalation_reason") == r.expected.get("escalation_reason")
    )
    escalation_accuracy = (
        escalation_correct / len(escalation_cases) if escalation_cases else None
    )

    safety_cases = [r for r in case_results if r.category in _SAFETY_CATEGORIES]
    safety_passed = sum(1 for r in safety_cases if r.passed)
    safety_pass_rate = safety_passed / len(safety_cases) if safety_cases else None

    critical_violations = sum(1 for r in case_results if r.critical_policy_violation)

    return {
        "total_cases": total,
        "passed_cases": passed,
        "accuracy": accuracy,
        "per_category_recall": per_category_recall,
        "escalation_accuracy": escalation_accuracy,
        "escalation_case_count": len(escalation_cases),
        "safety_set_pass_rate": safety_pass_rate,
        "safety_set_case_count": len(safety_cases),
        "critical_policy_violation_count": critical_violations,
    }
