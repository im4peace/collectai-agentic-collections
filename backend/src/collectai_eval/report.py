"""Human-readable report for one or two `EvalRunResult`s (E10-S1; reporting
rules E10-S2). The 30-case rule and every pass/fail-vs-observation-only
decision live in `reporting_rules.py`, not here -- this module only formats
whatever that pure logic already decided. MOCK and LIVE render in separate,
clearly labelled sections (`render_report` renders exactly one run;
`render_combined_report` renders both, one after the other, never merged):
a LIVE run's real model accuracy and a MOCK run's harness-only smoke check
answer different questions and must never be compared as if they were the
same metric (E10-S2 AC4)."""

from __future__ import annotations

from collectai_eval import reporting_rules
from collectai_eval.schemas import EvalRunResult

_MIN_CASES_FOR_CONFIDENCE = reporting_rules.MIN_CASES_FOR_CLAIM


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
    overall_claim = reporting_rules.evaluate_overall_accuracy_claim(
        accuracy=metrics["accuracy"], case_count=result.case_count, mode=result.mode
    )
    lines.append(
        f"accuracy:        {metrics['accuracy']:.2%} "
        f"({metrics['passed_cases']}/{metrics['total_cases']}) "
        f"[{overall_claim.status} vs "
        f"{reporting_rules.OVERALL_ACCURACY_TARGET:.0%} overall target]"
    )
    escalation = reporting_rules.compute_escalation_metrics(result.case_results)
    if metrics["escalation_accuracy"] is not None:
        lines.append(
            f"escalation_accuracy: {metrics['escalation_accuracy']:.2%} "
            f"({metrics['escalation_case_count']} scorable cases)"
        )
    lines.append(
        "escalation_precision: "
        f"{_render_ratio(escalation.precision)}  "
        f"escalation_recall: {_render_ratio(escalation.recall)}  "
        f"over_escalation_rate: {_render_ratio(escalation.over_escalation_rate)}"
    )

    safety = reporting_rules.evaluate_safety_set(result.case_results, mode=result.mode)
    lines.append(
        f"safety_set (VULNERABLE_CUSTOMER): {safety.case_count} cases, "
        f"{safety.critical_violation_count} critical policy violation(s) "
        "(missed escalation)"
    )
    if safety.pass_rate is not None:
        lines.append(f"safety_set_pass_rate: {safety.pass_rate:.2%}")
    else:
        lines.append(
            "safety_set_pass_rate: not published "
            f"(requires a LIVE run with >= {reporting_rules.MIN_CASES_FOR_CLAIM} labelled cases)"
        )

    category_metrics = reporting_rules.compute_category_metrics(result.case_results)
    category_claims = reporting_rules.evaluate_category_claims(category_metrics, mode=result.mode)
    lines.append("per_category_recall:")
    for category in sorted(category_claims):
        claim = category_claims[category]
        mandatory = " (mandatory-escalation)" if claim.mandatory_escalation_category else ""
        lines.append(
            f"  {category}{mandatory}: {claim.metric.recall:.2%} "
            f"(tp={claim.metric.true_positives} fn={claim.metric.false_negatives} "
            f"n={claim.metric.case_count}) [{claim.status}]"
        )

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


def render_combined_report(
    *, mock_result: EvalRunResult | None, live_result: EvalRunResult | None
) -> str:
    """AC4: MOCK and LIVE in separate sections, never merged -- each
    section is exactly `render_report`'s own output for that run, so a
    MOCK section can never carry a LIVE-only pass/fail claim (`render_report`
    itself only issues one when `result.mode == "LIVE"`). Either argument
    may be omitted (e.g. no LIVE run has ever been confirmed yet)."""
    sections: list[str] = []
    if mock_result is not None:
        sections.append(render_report(mock_result))
    if live_result is not None:
        sections.append(render_report(live_result))
    if not sections:
        return "=== Evaluation report ===\n(no runs to report)"
    return "\n\n".join(sections)



def _render_ratio(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"
