"""E10-S5 AC2: the generated P2 markdown report (`collectai_eval.report_markdown`
+ `store.load_latest_run` + the `report` CLI command). The renderer tests are
pure unit tests over hand-built results with known counts; only the store
round trip needs a database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from collectai_eval.cli import _build_arg_parser
from collectai_eval.datasets.loader import load_dataset
from collectai_eval.metrics import compute_metrics
from collectai_eval.report_markdown import render_markdown_report
from collectai_eval.schemas import EvalCaseResult, EvalRunResult, TokenUsage
from collectai_eval.store import load_latest_run, store_eval_run

_RUN_AT = datetime(2026, 9, 25, 10, 0, 0, tzinfo=UTC)


def _case(case_id: str, category: str, *, passed: bool = True) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case_id,
        category=category,
        expected={"intent": category, "escalation_reason": None},
        actual={"intent": category if passed else "UNKNOWN", "escalation_reason": None},
        passed=passed,
        critical_policy_violation=False,
    )


def _result(cases: list[EvalCaseResult], *, mode: str) -> EvalRunResult:
    return EvalRunResult(
        mode=mode,
        dataset_version="eval-ds-v1",
        dataset_provenance={},
        model_id="claude-test-model" if mode == "LIVE" else None,
        prompt_version="intent_v1",
        policy_version="policy-v1",
        run_at=_RUN_AT,
        case_results=cases,
        metrics=compute_metrics(cases),
        token_usage=TokenUsage(input_tokens=1200, output_tokens=300) if mode == "LIVE" else None,
        estimated_cost_usd=0.0123 if mode == "LIVE" else None,
        triggered_by="test",
    )


def _small_run(mode: str) -> EvalRunResult:
    return _result(
        [
            _case("d1", "DISPUTE"),
            _case("d2", "DISPUTE", passed=False),
            _case("h1", "FINANCIAL_HARDSHIP"),
        ],
        mode=mode,
    )


def _section(document: str, heading: str) -> str:
    start = document.index(f"## {heading}")
    following = document.find("\n## ", start + 1)
    return document[start : following if following != -1 else len(document)]


def test_mock_only_report_says_no_live_run_and_never_fills_it_from_mock() -> None:
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=_small_run("MOCK"), live_result=None
    )

    live = _section(document, "LIVE evaluation run")
    assert "**No LIVE run.**" in live
    assert "Nothing is estimated" in live
    assert "claude" not in live and "%" not in live
    mock = _section(document, "MOCK regression run")
    assert "never evidence of real-model quality" in mock


def test_every_per_category_row_shows_the_required_p2_fields() -> None:
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=_small_run("MOCK"), live_result=None
    )

    mock = _section(document, "MOCK regression run")
    assert (
        "| Category | Mandatory escalation | Cases | True positives | False negatives "
        "| Recall | Claim status |"
    ) in mock
    assert "| DISPUTE | yes | 2 | 1 | 1 | 50.00% | OBSERVATION_ONLY |" in mock
    assert "| FINANCIAL_HARDSHIP | yes | 1 | 1 | 0 | 100.00% | OBSERVATION_ONLY |" in mock
    # Model, prompt version, date and data label are stated for the run.
    assert "| Prompt version | intent_v1 |" in mock
    assert "| Evaluation date (UTC) | 2026-09-25 |" in mock
    assert "| Data label | MOCK |" in mock
    assert "| Model | (none - scripted MOCK provider) |" in mock


def test_provenance_lists_the_dataset_version_authorship_and_per_category_counts() -> None:
    dataset = load_dataset()
    document = render_markdown_report(dataset=dataset, mock_result=None, live_result=None)

    provenance = _section(document, "Dataset provenance")
    assert f"`{dataset.dataset_version}`" in provenance
    assert "Authorship method" in provenance
    assert "Synthetic statement" in provenance
    for category in {case.category for case in dataset.cases}:
        expected = sum(1 for case in dataset.cases if case.category == category)
        assert f"| {category} | {expected} |" in provenance
    assert "OBSERVATION_ONLY" in provenance  # the sample-size limitation is stated


def test_live_run_under_30_cases_per_category_never_claims_pass_or_fail() -> None:
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=None, live_result=_small_run("LIVE")
    )

    live = _section(document, "LIVE evaluation run")
    assert "| Model | claude-test-model |" in live
    assert "| Data label | LIVE |" in live
    assert "OBSERVATION_ONLY" in live
    assert "| PASS |" not in live and "| FAIL |" not in live
    assert "not published" in live  # the safety-set pass rate is withheld


def test_live_category_with_30_cases_shows_a_pass_against_the_95_percent_target() -> None:
    cases = [_case(f"d{index}", "DISPUTE") for index in range(30)]
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=None, live_result=_result(cases, mode="LIVE")
    )

    assert "| DISPUTE | yes | 30 | 30 | 0 | 100.00% | PASS |" in document


def test_a_mock_run_never_claims_pass_or_fail_even_with_30_cases() -> None:
    cases = [_case(f"d{index}", "DISPUTE") for index in range(30)]
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=_result(cases, mode="MOCK"), live_result=None
    )

    mock = _section(document, "MOCK regression run")
    assert "| PASS |" not in mock and "| FAIL |" not in mock
    assert "OBSERVATION_ONLY" in mock


def test_mock_and_live_are_separate_sections_and_never_merged() -> None:
    document = render_markdown_report(
        dataset=load_dataset(), mock_result=_small_run("MOCK"), live_result=_small_run("LIVE")
    )

    mock = _section(document, "MOCK regression run")
    live = _section(document, "LIVE evaluation run")
    assert "claude-test-model" not in mock
    assert "| Data label | MOCK |" not in live
    assert document.index("## MOCK regression run") < document.index("## LIVE evaluation run")


def test_report_command_defaults_to_the_p2_path() -> None:
    args = _build_arg_parser().parse_args(["report"])

    assert str(args.output).replace("\\", "/") == "docs/portfolio/ai-evaluation-report.md"


@pytest.mark.db
async def test_load_latest_run_round_trips_a_stored_run_and_never_crosses_modes(
    session: AsyncSession, policy_rule_set_row: None
) -> None:
    await store_eval_run(session, _small_run("MOCK"))

    loaded = await load_latest_run(session, "MOCK")

    assert loaded is not None
    assert loaded.mode == "MOCK"
    assert loaded.case_count == 3
    assert loaded.prompt_version == "intent_v1"
    assert loaded.run_at == _RUN_AT
    assert sorted(result.case_id for result in loaded.case_results) == ["d1", "d2", "h1"]
    assert loaded.metrics["passed_cases"] == 2
    assert await load_latest_run(session, "LIVE") is None
