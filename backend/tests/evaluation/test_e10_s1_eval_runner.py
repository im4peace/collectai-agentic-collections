"""E10-S1 AC2, AC3, AC4: the MOCK/LIVE runner, `eval_run`/`eval_case_result`
persistence, and metrics/report generation, against a real, migrated
Postgres database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import collectai_eval.runner as runner_module
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.persistence.orm.eval_case_result import EvalCaseResultOrm
from collectai.persistence.orm.eval_run import EvalRunOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import ProviderMode
from collectai_eval.datasets.loader import load_dataset
from collectai_eval.report import render_report
from collectai_eval.runner import (
    LiveEvalCiRefusedError,
    LiveEvalMissingApiKeyError,
    LiveEvalNotConfirmedError,
    LiveEvalTooManyCasesError,
    RunConfig,
    run_eval,
)
from collectai_eval.schemas import EvalDataset
from collectai_eval.store import store_eval_run

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)

# A small, fixed 6-case slice covering every required category at least
# once, keeping the DB-backed MOCK run in this test file fast -- the full
# default dataset is already validated separately (DB-free) in
# test_e10_s1_eval_dataset.py and test_eval_ds_v2_quality.py; this file's
# job is proving the *runner* works end to end, not re-running every case.
_SLICE_CASE_IDS = {"ev-001", "ev-007", "ev-019", "ev-025", "ev-031", "ev-037"}


def _small_dataset() -> EvalDataset:
    full = load_dataset()
    cases = [c for c in full.cases if c.case_id in _SLICE_CASE_IDS]
    assert len(cases) == len(_SLICE_CASE_IDS)
    return EvalDataset(
        dataset_version=full.dataset_version, provenance=full.provenance, cases=cases
    )


def _policy_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


async def test_ac2_mock_run_produces_governed_results_for_every_case(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    clock = SimulatedClock(_NOW)
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=_small_dataset(),
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )

    assert result.mode == "MOCK"
    assert result.model_id is None
    assert result.case_count == len(_SLICE_CASE_IDS)
    assert len(result.case_results) == len(_SLICE_CASE_IDS)
    for case_result in result.case_results:
        assert case_result.actual["governed"] is True
    # The MOCK provider is scripted with each case's own correct answer
    # (`_build_mock_provider`) -- if the harness's own scoring correctly
    # recognizes a right answer as a pass, this run's accuracy must be 100%.
    assert result.metrics["accuracy"] == 1.0
    assert all(case_result.passed for case_result in result.case_results)


def test_ac2_mock_provider_module_imports_no_networking_library() -> None:
    """`MockProvider.complete` never opens a socket (its own docstring:
    "zero network calls, ever") -- a structural check on its source module,
    since a runtime socket-block can't be layered onto this test file's own
    DB-backed run without also blocking the asyncpg connection every other
    test here needs. `AnthropicProvider`'s own module (`anthropic_live.py`,
    imported only for LIVE mode) is exactly where a real network call would
    have to originate instead."""
    import ast
    from pathlib import Path

    import collectai.llm_provider.mock as mock_module

    tree = ast.parse(Path(mock_module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    networking_libraries = {"socket", "http", "httpx", "requests", "aiohttp", "anthropic", "urllib"}
    assert not (imported & networking_libraries), imported & networking_libraries


async def test_ac2_mock_run_uses_the_mock_provider_not_a_real_one(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    from collectai.llm_provider.mock import MockProvider
    from collectai_eval.runner import _build_provider

    provider, model_id, provider_name = _build_provider(
        RunConfig(mode=ProviderMode.MOCK, triggered_by="test"), _small_dataset()
    )
    assert isinstance(provider, MockProvider)
    assert model_id is None
    assert provider_name == "mock"

    clock = SimulatedClock(_NOW)
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=_small_dataset(),
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    assert result.case_count == len(_SLICE_CASE_IDS)


async def test_ac3_live_refuses_without_confirmation(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    clock = SimulatedClock(_NOW)
    with pytest.raises(LiveEvalNotConfirmedError):
        await run_eval(
            session,
            session_factory=session_factory,
            dataset=_small_dataset(),
            config=RunConfig(
                mode=ProviderMode.LIVE, triggered_by="test", anthropic_api_key="sk-ant-fake"
            ),
            clock=clock,
            policy_provider=_policy_provider(clock),
        )


async def test_ac3_live_refuses_without_an_api_key(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    clock = SimulatedClock(_NOW)
    with pytest.raises(LiveEvalMissingApiKeyError):
        await run_eval(
            session,
            session_factory=session_factory,
            dataset=_small_dataset(),
            config=RunConfig(mode=ProviderMode.LIVE, triggered_by="test", live_confirmed=True),
            clock=clock,
            policy_provider=_policy_provider(clock),
        )


async def test_ac3_live_refuses_inside_ci_even_with_flag_and_key(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    clock = SimulatedClock(_NOW)
    with pytest.raises(LiveEvalCiRefusedError):
        await run_eval(
            session,
            session_factory=session_factory,
            dataset=_small_dataset(),
            config=RunConfig(
                mode=ProviderMode.LIVE,
                triggered_by="test",
                live_confirmed=True,
                anthropic_api_key="sk-ant-fake",
            ),
            clock=clock,
            policy_provider=_policy_provider(clock),
        )


async def test_ac4_stored_eval_run_carries_all_required_metadata(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    clock = SimulatedClock(_NOW)
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=_small_dataset(),
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test-ac4"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    eval_run_id = await store_eval_run(session, result)

    row = await session.get(EvalRunOrm, eval_run_id)
    assert row is not None
    assert row.mode == "MOCK"
    assert row.model_id is None  # CHECK (mode = 'LIVE' OR model_id IS NULL)
    assert row.dataset_version == "eval-ds-v2"
    assert row.prompt_version
    assert row.policy_version == "policy-v1"
    assert row.run_at == _NOW
    assert row.case_count == len(_SLICE_CASE_IDS)
    assert row.metrics["total_cases"] == len(_SLICE_CASE_IDS)
    assert row.triggered_by == "test-ac4"

    case_result_count = await session.scalar(
        select(func.count())
        .select_from(EvalCaseResultOrm)
        .where(EvalCaseResultOrm.eval_run_id == eval_run_id)
    )
    assert case_result_count == len(_SLICE_CASE_IDS)


async def test_report_renders_a_mock_section_with_the_stored_metrics(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    clock = SimulatedClock(_NOW)
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=_small_dataset(),
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    report = render_report(result)
    assert "MOCK run" in report
    assert "eval-ds-v2" in report
    assert "small-sample result" in report  # fewer than 30 cases in this slice


async def test_max_cases_refuses_before_provider_construction_or_any_case(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--max-cases` is checked before `_build_provider` is even called, not just before the
    case loop: this uses a LIVE config (a fake key, `live_confirmed=True`, no `CI` env var --
    the configuration that would otherwise reach `AnthropicProvider(...)`), and patches both
    `_build_provider` and `_run_one_case` to fail the test if either is ever called. Proves the
    ceiling refuses before a real provider is constructed, not merely before it is used."""

    def _fail_if_build_provider_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("_build_provider was called after max_cases should have refused")

    async def _fail_if_run_one_case_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("a case was attempted after max_cases should have refused the run")

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(runner_module, "_build_provider", _fail_if_build_provider_called)
    monkeypatch.setattr(runner_module, "_run_one_case", _fail_if_run_one_case_called)
    clock = SimulatedClock(_NOW)
    dataset = _small_dataset()
    with pytest.raises(LiveEvalTooManyCasesError) as exc_info:
        await run_eval(
            session,
            session_factory=session_factory,
            dataset=dataset,
            config=RunConfig(
                mode=ProviderMode.LIVE,
                triggered_by="test",
                live_confirmed=True,
                anthropic_api_key="sk-ant-fake",
                anthropic_model="claude-fake",
                max_cases=len(dataset.cases) - 1,
            ),
            clock=clock,
            policy_provider=_policy_provider(clock),
        )
    assert exc_info.value.resolved_case_count == len(dataset.cases)
    assert exc_info.value.max_cases == len(dataset.cases) - 1


async def test_max_cases_at_the_resolved_count_does_not_refuse(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    """The ceiling is `>`, not `>=`: a `--max-cases` equal to the resolved count is not a
    refusal -- it is the exact case count the operator asked to allow."""
    clock = SimulatedClock(_NOW)
    dataset = _small_dataset()
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=dataset,
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test", max_cases=len(dataset.cases)),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    assert result.case_count == len(dataset.cases)


async def test_omitting_max_cases_changes_nothing(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
) -> None:
    """`max_cases=None` (the default) is exactly today's behaviour: no ceiling, every case in
    the resolved dataset runs, regardless of size."""
    clock = SimulatedClock(_NOW)
    dataset = _small_dataset()
    result = await run_eval(
        session,
        session_factory=session_factory,
        dataset=dataset,
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    assert result.case_count == len(dataset.cases)


async def test_resolved_dataset_and_case_count_are_logged_before_any_case_runs(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator-facing safety print from the LIVE-baseline design: mode, dataset_version,
    case_count and max_cases (when supplied) are all logged before the run can do anything,
    MOCK included, so the same log line is exercised here without any real provider call. Spies
    on the module's own `logger.info` directly (rather than `caplog`) so this is independent of
    any interaction between pytest's log-capture handler and this project's async/embedded-
    postgres fixture chain."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        runner_module.logger, "info", lambda *args, **kwargs: calls.append(args)
    )
    clock = SimulatedClock(_NOW)
    dataset = _small_dataset()
    await run_eval(
        session,
        session_factory=session_factory,
        dataset=dataset,
        config=RunConfig(
            mode=ProviderMode.MOCK, triggered_by="test", max_cases=len(dataset.cases) + 5
        ),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    assert calls, "logger.info was never called"
    logged = calls[0]
    assert ProviderMode.MOCK.value in logged
    assert dataset.dataset_version in logged
    assert len(dataset.cases) in logged  # case_count
    assert len(dataset.cases) + 5 in logged  # max_cases, a distinct value from case_count


async def test_the_preflight_log_names_no_max_cases_when_it_was_omitted(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    policy_rule_set_row: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`max_cases` omitted (the default) must not be logged as if a ceiling were set."""
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        runner_module.logger, "info", lambda *args, **kwargs: calls.append(args)
    )
    clock = SimulatedClock(_NOW)
    dataset = _small_dataset()
    await run_eval(
        session,
        session_factory=session_factory,
        dataset=dataset,
        config=RunConfig(mode=ProviderMode.MOCK, triggered_by="test"),
        clock=clock,
        policy_provider=_policy_provider(clock),
    )
    assert calls, "logger.info was never called"
    assert calls[0][-1] == "(none)"
