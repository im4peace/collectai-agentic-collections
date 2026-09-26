"""Generator for `eval_ds_v2.json` and its human-review sheet (E10-S1 AC6).

Run once (`python -m collectai_eval.datasets._build_eval_ds_v2`) to (re)write the two checked-in
files; the dataset is a static, versioned artifact thereafter, never regenerated at runtime, so
results stay comparable across runs of the same `dataset_version`.

`eval-ds-v2` = the 60 `eval-ds-v1` cases (read from `eval_ds_v1.json`, which this module never
writes) with 13 explicit escalation-reason corrections, plus the case banks `_v2_sensitive_a`,
`_v2_sensitive_b` and `_v2_general`. Ids `ev-001`..`ev-060` are v1's; new ids follow in bank order.
The builder refuses to write anything if `quality.run_all_checks` finds a problem.

Authorship is stated honestly in the provenance: the new cases were drafted by Claude (an LLM)
against `EVAL_DS_V2_LABELLING_RUBRIC.md`. No human has reviewed the labels yet.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from collectai_eval.datasets import _v2_general, _v2_sensitive_a, _v2_sensitive_b, quality
from collectai_eval.datasets._v2_common import NewCase
from collectai_eval.datasets.loader import DATASET_V1_PATH, DATASET_V2_PATH, parse_dataset

REVIEW_SHEET_PATH = Path(__file__).resolve().parent / "EVAL_DS_V2_REVIEW_SHEET.md"
DATASET_VERSION = "eval-ds-v2"
PARENT_VERSION = "eval-ds-v1"
EXPECTED_TOTAL = 264
EXPECTED_COUNTS = {
    "ADVERSARIAL": 14,
    "AMBIGUOUS_VALIDATION": 4,
    "DISPUTE": 30,
    "EDGE": 12,
    "FINANCIAL_HARDSHIP": 30,
    "PAYMENT_PLAN": 14,
    "PAY_NOW": 14,
    "POLICY_EXCEPTION": 30,
    "POLICY_SETTLEMENT": 30,
    "PROMISE_TO_PAY": 14,
    "REQUEST_HUMAN": 30,
    "UNKNOWN": 12,
    "VULNERABLE_CUSTOMER": 30,
}

# The 13 v1 cases whose expected_escalation_reason was null although the runner's own precedence
# yields a reason for their intent label (found by `quality.check_escalation_consistency`).
LABEL_CORRECTIONS: dict[str, str] = {
    **{f"ev-{number:03d}": "FINANCIAL_HARDSHIP" for number in range(19, 25)},
    **{f"ev-{number:03d}": "DISPUTE" for number in range(25, 31)},
    "ev-049": "DISPUTE",
}

# Human-review plan: every case in the sensitive categories, plus this fixed sample of the rest
# (every Nth case in id order, starting with the first).
_SAMPLE_STEP = {"EDGE": 2, "ADVERSARIAL": 2, "AMBIGUOUS_VALIDATION": 2}
_DEFAULT_SAMPLE_STEP = 3
_REVIEW_STATUS = "NOT REVIEWED - PENDING"


def _new_cases() -> list[NewCase]:
    return [*_v2_sensitive_a.CASES, *_v2_sensitive_b.CASES, *_v2_general.CASES]


def _case_record(case_id: str, case: NewCase) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "category": case.category,
        "message": case.message,
        "expected_intent": case.expected_intent,
        "expected_vulnerability_detected": case.vulnerability_category is not None,
        "expected_vulnerability_category": case.vulnerability_category,
        "expected_special_request": case.special_request,
        "expected_escalation_reason": case.escalation_reason,
    }


def _provenance(v1: dict[str, Any], new_count: int) -> dict[str, str]:
    corrected = ", ".join(LABEL_CORRECTIONS)
    return {
        "authorship_method": (
            f"Cases ev-001 to ev-060 are inherited unchanged from {PARENT_VERSION} (hand-authored "
            f"phrasing templates, assembled programmatically). Cases ev-061 to "
            f"ev-{60 + new_count:03d} ({new_count} cases) are AI-assisted: drafted by Claude (an "
            "LLM) against the written labelling rubric in "
            "datasets/EVAL_DS_V2_LABELLING_RUBRIC.md and assembled by "
            "collectai_eval/datasets/_build_eval_ds_v2.py. No real customer content was used."
        ),
        "synthetic_statement": v1["provenance"]["synthetic_statement"],
        "parent_version": PARENT_VERSION,
        "change_summary": (
            f"Adds {new_count} cases (60 to {60 + new_count}) so that each of FINANCIAL_HARDSHIP, "
            "DISPUTE, REQUEST_HUMAN, POLICY_EXCEPTION, POLICY_SETTLEMENT and VULNERABLE_CUSTOMER "
            "has 30 cases and every other category has 4 to 14. "
            f"{PARENT_VERSION} is unchanged and remains the historical artifact. Existing case "
            "ids, messages and intent labels are unchanged; only the label corrections listed "
            "below differ."
        ),
        "label_corrections": (
            f"{len(LABEL_CORRECTIONS)} expected_escalation_reason values changed from null: "
            "ev-019 to ev-024 -> FINANCIAL_HARDSHIP; ev-025 to ev-030 -> DISPUTE; "
            "ev-049 -> DISPUTE. Reason: the runner's safety precedence predicts these reasons "
            "for every hardship or dispute intent, so null overstated over-escalation "
            f"({corrected}). No other v1 field was changed."
        ),
        "human_review_status": (
            f"{_REVIEW_STATUS}. No human has reviewed these labels. Plan: every case in the six "
            "sensitive categories plus a fixed sample of the others (datasets/"
            "EVAL_DS_V2_REVIEW_SHEET.md). A MOCK run does not validate labels: the MOCK provider "
            "is scripted with each case's own expected answer."
        ),
        "labelling_rubric": "datasets/EVAL_DS_V2_LABELLING_RUBRIC.md",
        "known_limitations": (
            "Category POLICY_SETTLEMENT is not the name in reporting_rules."
            "MANDATORY_ESCALATION_CATEGORIES (SETTLEMENT_REQUEST), so reports show it as not "
            "mandatory-escalation; EXCEPTIONAL_ARRANGEMENT has no cases because it cannot be "
            "decided from one message. AMBIGUOUS_VALIDATION cases are documentation-only "
            "(state-dependent) and count as escalation false negatives in the escalation "
            "metrics. The inherited v1 cases ev-053 and ev-054 have arguable intent labels and "
            "are unchanged pending review. Single-message classification only; no held-out "
            "split; results describe this dataset only."
        ),
    }


def build_dataset() -> dict[str, Any]:
    v1 = json.loads(DATASET_V1_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = [dict(case) for case in v1["cases"]]
    for case in cases:
        corrected = LABEL_CORRECTIONS.get(case["case_id"])
        if corrected is not None:
            if case["expected_escalation_reason"] is not None:
                raise ValueError(f"{case['case_id']} is not null in {PARENT_VERSION}")
            case["expected_escalation_reason"] = corrected
    new_cases = _new_cases()
    for offset, new_case in enumerate(new_cases, start=len(cases) + 1):
        cases.append(_case_record(f"ev-{offset:03d}", new_case))
    return {
        "dataset_version": DATASET_VERSION,
        "provenance": _provenance(v1, len(new_cases)),
        "cases": cases,
    }


def _cell(text: object) -> str:
    return "-" if text is None else str(text).replace("|", "\\|")


def _row(case: dict[str, Any]) -> str:
    return (
        f"| {case['case_id']} | {_cell(case['message'])} | {case['expected_intent']} "
        f"| {'yes' if case['expected_vulnerability_detected'] else 'no'} "
        f"| {_cell(case['expected_vulnerability_category'])} "
        f"| {case['expected_special_request']} | {_cell(case['expected_escalation_reason'])} | | |"
    )


_HEADER = (
    "| Case | Message | Intent | Vulnerable | Vulnerability category | Special request "
    "| Escalation reason | Verdict | Notes |\n|---|---|---|---|---|---|---|---|---|"
)


def render_review_sheet(dataset: dict[str, Any]) -> str:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in dataset["cases"]:
        by_category[case["category"]].append(case)
    sensitive = list(quality.SENSITIVE_CATEGORIES)
    sample = [c for c in sorted(by_category) if c not in quality.SENSITIVE_CATEGORIES]

    full_total = sum(len(by_category[c]) for c in sensitive)
    lines = [
        f"# {dataset['dataset_version']} human review sheet",
        "",
        f"**Status: {_REVIEW_STATUS}.** Nobody has reviewed these labels yet. Reviewer and date "
        "are deliberately blank; fill them in only when a review actually happens.",
        "",
        "Reviewer: ______________________   Date: ______________________",
        "",
        "For each row, read the message and confirm every expected field against "
        "`EVAL_DS_V2_LABELLING_RUBRIC.md`. Verdict: `OK`, `WRONG` (write the correct label in "
        "Notes) or `AMBIGUOUS` (the case should be rewritten or dropped). A MOCK run cannot do "
        "this check: it is scripted with these same expected answers.",
        "",
        f"## Full review: the six sensitive categories ({full_total} cases)",
        "",
    ]
    for category in sensitive:
        lines += [f"### {category} ({len(by_category[category])})", "", _HEADER]
        lines += [_row(case) for case in by_category[category]]
        lines.append("")

    sampled: dict[str, list[dict[str, Any]]] = {}
    for category in sample:
        step = _SAMPLE_STEP.get(category, _DEFAULT_SAMPLE_STEP)
        sampled[category] = by_category[category][::step]
    sample_total = sum(len(rows) for rows in sampled.values())
    lines += [
        f"## Sample review: the other categories ({sample_total} of "
        f"{sum(len(by_category[c]) for c in sample)} cases)",
        "",
        "Selection rule: within each category, in case-id order, every 2nd case (EDGE, "
        "ADVERSARIAL, AMBIGUOUS_VALIDATION) or every 3rd case (the rest), starting with the "
        "first.",
        "",
    ]
    for category, rows in sampled.items():
        lines += [f"### {category} ({len(rows)} of {len(by_category[category])})", "", _HEADER]
        lines += [_row(case) for case in rows]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    dataset = build_dataset()
    findings = quality.run_all_checks(
        parse_dataset(dataset).cases,
        total=EXPECTED_TOTAL,
        per_category=EXPECTED_COUNTS,
        minimum_categories=quality.SENSITIVE_CATEGORIES,
    )
    if findings:
        for finding in findings:
            print(f"{finding.check} {finding.case_ids}: {finding.detail}")
        raise SystemExit(f"{len(findings)} quality finding(s); nothing was written")
    # LF line endings on every platform, so the checked-in bytes are reproducible.
    DATASET_V2_PATH.write_bytes((json.dumps(dataset, indent=2) + "\n").encode("utf-8"))
    REVIEW_SHEET_PATH.write_bytes(render_review_sheet(dataset).encode("utf-8"))
    print(f"Wrote {len(dataset['cases'])} cases to {DATASET_V2_PATH}")
    print(f"Wrote review sheet to {REVIEW_SHEET_PATH}")


if __name__ == "__main__":
    main()
