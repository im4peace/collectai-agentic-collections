"""Human-readable report for one `EvalRunResult` (E10-S1). The "30-case
rule": a metric is only reported as statistically meaningful once it is
computed over at least 30 cases -- below that, the report still shows the
raw numbers but labels them a small-sample result rather than implying a
confident accuracy figure. MOCK and LIVE render in separate, clearly
labelled sections (this module never merges the two): a LIVE run's real
model accuracy and a MOCK run's harness-only smoke check answer different
questions and must never be compared as if they were the same metric.
"""

from __future__ import annotations

from collectai_eval.schemas import EvalRunResult

_MIN_CASES_FOR_CONFIDENCE = 30


def render_report(result: EvalRunResult) -> str:
    lines: list[str] = []
    section = "LIVE" if result.mode == "LIVE" else "MOCK"
    lines.append(f"=== Evaluation report: {section} run ===")
    lines.append(f"dataset_version: {result.dataset_version}")
    lines.append(f"prompt_version:  {result.prompt_version}")
    lines.append(f"policy_version:  {result.policy_version}")
    lines.append(f"model_id:        {result.model_id or '(MOCK -- no real model)'}")
    lines.append(f"run_at:          {result.run_at.isoformat()}")
    lines.append(f"triggered_by:    {result.triggered_by}")
    lines.append(f"case_count:      {result.case_count}")
    if result.case_count < _MIN_CASES_FOR_CONFIDENCE:
        lines.append(
            f"NOTE: fewer than {_MIN_CASES_FOR_CONFIDENCE} cases -- treat accuracy below as a "
            "small-sample result, not a confident estimate."
        )

    metrics = result.metrics
    lines.append(
        f"accuracy:        {metrics['accuracy']:.2%} "
        f"({metrics['passed_cases']}/{metrics['total_cases']})"
    )
    if metrics["escalation_accuracy"] is not None:
        lines.append(
            f"escalation_accuracy: {metrics['escalation_accuracy']:.2%} "
            f"({metrics['escalation_case_count']} scorable cases)"
        )
    if metrics["safety_set_pass_rate"] is not None:
        lines.append(
            f"safety_set_pass_rate: {metrics['safety_set_pass_rate']:.2%} "
            f"({metrics['safety_set_case_count']} cases)"
        )
    lines.append(f"critical_policy_violations: {metrics['critical_policy_violation_count']}")

    lines.append("per_category_recall:")
    for category, recall in sorted(metrics["per_category_recall"].items()):
        lines.append(f"  {category}: {recall:.2%}")

    if result.token_usage is not None:
        lines.append(
            f"token_usage: input={result.token_usage.input_tokens} "
            f"output={result.token_usage.output_tokens}"
        )
    if result.estimated_cost_usd is not None:
        lines.append(f"estimated_cost_usd: {result.estimated_cost_usd:.6f}")

    failed = [r for r in result.case_results if not r.passed]
    if failed:
        lines.append(f"failed cases ({len(failed)}):")
        for case_result in failed:
            lines.append(
                f"  {case_result.case_id} [{case_result.category}]: "
                f"expected={case_result.expected} actual={case_result.actual}"
            )

    return "\n".join(lines)
