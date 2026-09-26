"""Markdown rendering of the AI evaluation report -- portfolio deliverable P2,
`docs/portfolio/ai-evaluation-report.md` (E10-S5 AC2, BRD 4.4/15).

Generated, never hand-edited: `python -m collectai_eval report` reads the most
recent stored MOCK run and the most recent stored LIVE run and renders both.
Like `report.py`, this module only *formats*: every pass/fail-versus-
observation-only decision comes from `reporting_rules` (the 30-case rule,
D-025), so the document can never claim more than the rules allow. MOCK and
LIVE are always separate sections and are never merged or compared (BRD 4.6);
a missing LIVE run is stated plainly as "No LIVE run".
"""

from __future__ import annotations

from collections import Counter

from collectai_eval import reporting_rules
from collectai_eval.schemas import EvalDataset, EvalRunResult

_MIN = reporting_rules.MIN_CASES_FOR_CLAIM


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_percent(value: float | None) -> str:
    return _percent(value) if value is not None else "n/a"


def _have(count: int) -> str:
    return f"{count} category has" if count == 1 else f"{count} categories have"


def _sample_size_paragraph(
    dataset: EvalDataset, counts: Counter[str], live_result: EvalRunResult | None
) -> str:
    """The wording follows the data: which categories reach the 30-case minimum, and whether a
    LIVE run exists. It never says more than `reporting_rules` allows (D-025)."""
    smallest = min(counts.values()) if counts else 0
    largest = max(counts.values()) if counts else 0
    enough = sorted(category for category, count in counts.items() if count >= _MIN)
    short = sorted((category, count) for category, count in counts.items() if count < _MIN)
    parts = [
        "**Sample-size limitation.** The dataset is self-authored: "
        f"{len(dataset.cases)} cases across {len(counts)} categories, "
        f"between {smallest} and {largest} per category. A per-category recall claim "
        f"needs at least {_MIN} labelled LIVE cases (BRD 4.4, D-025)."
    ]
    if enough:
        parts.append(
            f"{_have(len(enough))} at least {_MIN} labelled cases ({', '.join(enough)}), so "
            "they could carry a claim once a LIVE run exists; that is a precondition, not "
            "evidence of quality."
        )
    if short:
        listed = ", ".join(f"{category} ({count})" for category, count in short)
        parts.append(
            f"{_have(len(short))} fewer ({listed}) and stay **OBSERVATION_ONLY** even in a "
            "LIVE run."
        )
    if live_result is None:
        parts.append(
            "No LIVE run has been stored, so **every per-category result is OBSERVATION_ONLY** "
            "-- reported as counts, never as a pass or fail."
        )
    else:
        parts.append(
            f"Only categories with at least {_MIN} labelled cases can show PASS or FAIL in the "
            "LIVE section; every other category, and every MOCK result, is OBSERVATION_ONLY."
        )
    parts.append("There is no held-out split. Results describe performance on this dataset only.")
    return " ".join(parts)


def _dataset_section(dataset: EvalDataset, live_result: EvalRunResult | None) -> list[str]:
    counts = Counter(case.category for case in dataset.cases)
    lines = [
        "## Dataset provenance",
        "",
        f"- **Dataset version:** `{dataset.dataset_version}`",
        f"- **Labelled cases:** {len(dataset.cases)}",
    ]
    for key in sorted(dataset.provenance):
        lines.append(f"- **{key.replace('_', ' ').capitalize()}:** {dataset.provenance[key]}")
    lines += [
        "",
        "| Category | Cases |",
        "|---|---|",
        *[f"| {category} | {counts[category]} |" for category in sorted(counts)],
        "",
        _sample_size_paragraph(dataset, counts, live_result),
        "",
    ]
    return lines


def _run_section(title: str, result: EvalRunResult | None, *, mode: str) -> list[str]:
    lines = [f"## {title}", ""]
    if result is None:
        if mode == "LIVE":
            lines += [
                "**No LIVE run.** No LIVE evaluation run has been stored. LIVE runs are "
                "manual, use a paid API and are never executed in CI. Nothing is estimated "
                "and nothing is copied from the MOCK run.",
                "",
            ]
        else:
            lines += ["**No MOCK run.** No MOCK evaluation run has been stored.", ""]
        return lines

    if mode == "MOCK":
        lines += [
            "> MOCK results exercise the evaluation harness against a scripted provider. "
            "They are a regression check and are **never evidence of real-model quality**.",
            "",
        ]
    metrics = result.metrics
    lines += [
        "| Field | Value |",
        "|---|---|",
        f"| Data label | {mode} |",
        f"| Evaluation date (UTC) | {result.run_at.date().isoformat()} |",
        f"| Model | {result.model_id or '(none - scripted MOCK provider)'} |",
        f"| Prompt version | {result.prompt_version} |",
        f"| Policy version | {result.policy_version} |",
        f"| Dataset version | {result.dataset_version} |",
        f"| Cases | {result.case_count} |",
        f"| Triggered by | {result.triggered_by} |",
    ]
    if result.token_usage is not None:
        lines.append(
            f"| Tokens (input / output) | {result.token_usage.input_tokens} / "
            f"{result.token_usage.output_tokens} |"
        )
    if result.estimated_cost_usd is not None:
        lines.append(f"| Estimated cost (USD, an estimate) | {result.estimated_cost_usd:.6f} |")

    overall = reporting_rules.evaluate_overall_accuracy_claim(
        accuracy=metrics["accuracy"], case_count=result.case_count, mode=result.mode
    )
    lines += [
        "",
        f"Overall intent accuracy: {_percent(metrics['accuracy'])} "
        f"({metrics['passed_cases']}/{metrics['total_cases']}) -- claim status "
        f"**{overall.status}**"
        + (
            f" against the {_percent(reporting_rules.OVERALL_ACCURACY_TARGET)} target."
            if mode == "LIVE"
            else " (MOCK is never compared to a target)."
        ),
        "",
        "### Per-category results",
        "",
        "| Category | Mandatory escalation | Cases | True positives | False negatives "
        "| Recall | Claim status |",
        "|---|---|---|---|---|---|---|",
    ]
    category_metrics = reporting_rules.compute_category_metrics(result.case_results)
    claims = reporting_rules.evaluate_category_claims(category_metrics, mode=result.mode)
    for category in sorted(claims):
        claim = claims[category]
        item = claim.metric
        lines.append(
            f"| {category} | {'yes' if claim.mandatory_escalation_category else 'no'} "
            f"| {item.case_count} | {item.true_positives} | {item.false_negatives} "
            f"| {_percent(item.recall)} | {claim.status} |"
        )

    escalation = reporting_rules.compute_escalation_metrics(result.case_results)
    safety = reporting_rules.evaluate_safety_set(result.case_results, mode=result.mode)
    lines += [
        "",
        "### Escalation and safety",
        "",
        f"- Escalation precision: {_optional_percent(escalation.precision)}; "
        f"recall: {_optional_percent(escalation.recall)}; "
        f"over-escalation rate: {_optional_percent(escalation.over_escalation_rate)}",
        f"- Vulnerable-customer safety set: {safety.case_count} cases, "
        f"{safety.critical_violation_count} critical policy violation(s) (missed escalation)",
        "- Safety-set pass rate: "
        + (
            _percent(safety.pass_rate)
            if safety.pass_rate is not None
            else f"not published (needs a LIVE run with at least {_MIN} labelled cases)"
        ),
        "",
    ]
    return lines


def render_markdown_report(
    *,
    dataset: EvalDataset,
    mock_result: EvalRunResult | None,
    live_result: EvalRunResult | None,
) -> str:
    """The full P2 document. MOCK and LIVE are rendered as two separate
    sections; either may be absent."""
    lines = [
        "# AI evaluation report (P2)",
        "",
        "_Generated by `python -m collectai_eval report` from stored evaluation runs. "
        "Do not edit by hand -- regenerate it._",
        "",
        "Reading rules (BRD 4.4, 4.6): MOCK and LIVE are always reported separately. "
        "MOCK is regression-only. Intent-accuracy and recall claims come only from LIVE "
        f"runs, and a per-category recall claim needs at least {_MIN} labelled LIVE cases.",
        "",
        *_dataset_section(dataset, live_result),
        *_run_section("MOCK regression run", mock_result, mode="MOCK"),
        *_run_section("LIVE evaluation run", live_result, mode="LIVE"),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"
