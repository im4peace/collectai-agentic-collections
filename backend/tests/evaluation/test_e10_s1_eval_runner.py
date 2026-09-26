"""E10-S1 AC2, AC3, AC4: the MOCK/LIVE runner, `eval_run`/`eval_case_result`
persistence, and metrics/report generation, against a real, migrated
Postgres database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    provider, model_id = _build_provider(
        RunConfig(mode=ProviderMode.MOCK, triggered_by="test"), _small_dataset()
    )
    assert isinstance(provider, MockProvider)
    assert model_id is None

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
