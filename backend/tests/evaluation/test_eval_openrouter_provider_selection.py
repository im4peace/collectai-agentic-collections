"""OpenRouter LIVE-provider selection and safety-guard tests for `collectai_eval.runner`
(mirrors `test_e10_s1_eval_cli_args.py`'s CLI-arg-only scope, one level in: pure
`_build_provider`/`run_eval` behaviour, no database, no provider construction reaching the
network).

No real network calls are made anywhere in this file: `OpenRouterProvider`'s own HTTP
behaviour is exercised separately, with a fully mocked `httpx.AsyncClient`, in
`backend/tests/unit/llm_provider/test_openrouter_live.py`. Every test here either expects a
refusal before a provider is ever constructed, or only inspects the constructed provider's
type/attributes -- `OpenRouterProvider.__init__` builds an `httpx.AsyncClient` but never
connects, matching `AnthropicProvider.__init__`'s own no-network-at-construction-time
behaviour.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

import collectai_eval.runner as runner_module
from collectai.llm_provider.anthropic_live import AnthropicProvider
from collectai.llm_provider.mock import MockProvider
from collectai.llm_provider.openrouter_live import OpenRouterProvider
from collectai.types.enums import ProviderMode
from collectai_eval.runner import (
    LiveEvalCiRefusedError,
    LiveEvalMissingOpenRouterApiKeyError,
    LiveEvalMissingOpenRouterModelError,
    LiveEvalNotConfirmedError,
    LiveEvalOpenRouterModelNotFreeError,
    LiveEvalTooManyCasesError,
    RunConfig,
    _build_provider,
    run_eval,
)
from collectai_eval.schemas import EvalCase, EvalDataset

pytestmark = pytest.mark.unit


def _dataset(n: int = 1) -> EvalDataset:
    cases = [
        EvalCase(
            case_id=f"ev-{i:03d}",
            category="PAY_NOW",
            message="I want to pay the overdue amount right now.",
            expected_intent="PAY_NOW",
            expected_vulnerability_detected=False,
            expected_vulnerability_category=None,
            expected_special_request="NONE",
            expected_escalation_reason=None,
        )
        for i in range(n)
    ]
    return EvalDataset(dataset_version="test-ds", provenance={}, cases=cases)


def _openrouter_config(**overrides: Any) -> RunConfig:
    fields: dict[str, Any] = {
        "mode": ProviderMode.LIVE,
        "triggered_by": "test",
        "live_confirmed": True,
        "provider": "openrouter",
        "openrouter_api_key": "sk-or-fake",
        "openrouter_model": "vendor/model:free",
    }
    fields.update(overrides)
    return RunConfig(**fields)


# C: existing Anthropic provider construction is unaffected by the OpenRouter addition
# (_build_provider's return shape grew a third element, but the Anthropic branch itself did
# not change).
def test_anthropic_provider_construction_remains_unchanged_when_provider_omitted() -> None:
    provider, model_id, provider_name = _build_provider(
        RunConfig(
            mode=ProviderMode.LIVE,
            triggered_by="test",
            live_confirmed=True,
            anthropic_api_key="sk-ant-fake",
            anthropic_model="claude-fake",
        ),
        _dataset(),
    )
    assert isinstance(provider, AnthropicProvider)
    assert model_id == "claude-fake"
    assert provider_name == "anthropic"


# D & H: a fully-configured OpenRouter RunConfig with a valid ":free" model builds an
# OpenRouterProvider.
def test_openrouter_provider_selection_works_with_a_valid_free_model() -> None:
    provider, model_id, provider_name = _build_provider(_openrouter_config(), _dataset())

    assert isinstance(provider, OpenRouterProvider)
    assert model_id == "vendor/model:free"
    assert provider_name == "openrouter"


# E: missing OPENROUTER_API_KEY fails before any network access (before OpenRouterProvider
# is even constructed).
def test_openrouter_missing_api_key_fails_before_provider_construction() -> None:
    with pytest.raises(LiveEvalMissingOpenRouterApiKeyError):
        _build_provider(_openrouter_config(openrouter_api_key=None), _dataset())


# F: missing OPENROUTER_MODEL fails before any network access.
def test_openrouter_missing_model_fails_before_provider_construction() -> None:
    with pytest.raises(LiveEvalMissingOpenRouterModelError):
        _build_provider(_openrouter_config(openrouter_model=None), _dataset())


# G: a syntactically valid model id that does not end in ":free" is refused -- the dedicated
# safety guard against accidental paid-model usage, with no override flag.
def test_openrouter_non_free_model_is_refused() -> None:
    with pytest.raises(LiveEvalOpenRouterModelNotFreeError) as exc_info:
        _build_provider(_openrouter_config(openrouter_model="vendor/model"), _dataset())
    assert exc_info.value.model == "vendor/model"


@pytest.mark.parametrize(
    "model",
    ["vendor/model:free-tier", "vendor/model:Free", "vendor/model:free2", "freemium/model"],
)
def test_openrouter_near_miss_free_suffixes_are_still_refused(model: str) -> None:
    """The guard checks an exact, case-sensitive ':free' suffix -- not a substring match --
    so a model id that merely contains "free" without ending in exactly ':free' is refused."""
    with pytest.raises(LiveEvalOpenRouterModelNotFreeError):
        _build_provider(_openrouter_config(openrouter_model=model), _dataset())


# I: CI refusal occurs before provider construction/network access for OpenRouter too -- the
# CI check runs before the anthropic/openrouter branch, so a fully-configured (but fake)
# OpenRouter config is still refused under CI.
def test_openrouter_ci_refusal_occurs_before_the_provider_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(LiveEvalCiRefusedError):
        _build_provider(_openrouter_config(), _dataset())


# J: --live-confirm remains mandatory for OpenRouter.
def test_openrouter_live_confirm_is_mandatory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    with pytest.raises(LiveEvalNotConfirmedError):
        _build_provider(_openrouter_config(live_confirmed=False), _dataset())


# K: --max-cases still refuses before _build_provider is even called, for the OpenRouter
# branch, exactly as it already does for Anthropic
# (test_max_cases_refuses_before_provider_construction_or_any_case in
# test_e10_s1_eval_runner.py). `run_eval` never touches `session`/`session_factory`/`clock`/
# `policy_provider` before the max_cases check runs, so dummy `None`s stand in for all four --
# if that stopped being true, this test would fail with an AttributeError on the dummy instead
# of silently passing.
async def test_openrouter_max_cases_refuses_before_build_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_build_provider_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("_build_provider was called after max_cases should have refused")

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(runner_module, "_build_provider", _fail_if_build_provider_called)
    dataset = _dataset(3)

    with pytest.raises(LiveEvalTooManyCasesError) as exc_info:
        await run_eval(
            cast(Any, None),
            session_factory=cast(Any, None),
            dataset=dataset,
            config=_openrouter_config(max_cases=len(dataset.cases) - 1),
            clock=cast(Any, None),
            policy_provider=cast(Any, None),
        )
    assert exc_info.value.resolved_case_count == len(dataset.cases)
    assert exc_info.value.max_cases == len(dataset.cases) - 1


# P: MOCK behaviour is unchanged -- _build_provider still returns "mock" as the provider_name
# even when --provider openrouter was also passed (provider selection is LIVE-only).
def test_mock_mode_ignores_the_provider_flag() -> None:
    provider, model_id, provider_name = _build_provider(
        RunConfig(mode=ProviderMode.MOCK, triggered_by="test", provider="openrouter"),
        _dataset(),
    )
    assert isinstance(provider, MockProvider)
    assert model_id is None
    assert provider_name == "mock"


# O: `_run_one_case` no longer hardcodes provider_name="anthropic" -- it uses whichever
# provider_name `_build_provider` resolved, so an OpenRouter LIVE run's audit trail is
# correctly labelled "openrouter", and an Anthropic LIVE run remains labelled "anthropic".
@pytest.mark.parametrize("expected_provider_name", ["anthropic", "openrouter", "mock"])
async def test_run_one_case_uses_the_resolved_provider_name_in_the_audit_call_context(
    monkeypatch: pytest.MonkeyPatch, expected_provider_name: str
) -> None:
    captured: dict[str, object] = {}

    class _FakeSafeState:
        value = "UNGOVERNED"

    class _FakeResult:
        structured_output = None
        governed = False
        safe_state = _FakeSafeState()

    async def _fake_run_ai_interaction(
        provider: object,
        request: object,
        schema: object,
        call_context: object,
        audit_service: object,
        **kwargs: object,
    ) -> _FakeResult:
        captured["provider_name"] = call_context.provider_name  # type: ignore[attr-defined]
        return _FakeResult()

    async def _fake_read_back_token_usage(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(runner_module, "run_ai_interaction", _fake_run_ai_interaction)
    monkeypatch.setattr(
        runner_module, "_read_back_token_usage", _fake_read_back_token_usage
    )

    case = _dataset(1).cases[0]
    await runner_module._run_one_case(
        cast(Any, None),
        case=case,
        provider=cast(Any, None),
        provider_mode=ProviderMode.LIVE,
        provider_name=expected_provider_name,
        audit_service=cast(Any, None),
    )

    assert captured["provider_name"] == expected_provider_name
