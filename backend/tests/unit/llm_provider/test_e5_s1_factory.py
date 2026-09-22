"""Tests for provider selection by configuration (E5-S1 AC1)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from collectai.config.settings import Settings
from collectai.llm_provider.anthropic_live import AnthropicProvider
from collectai.llm_provider.factory import MissingLiveCredentialsError, get_provider
from collectai.llm_provider.mock import MockProvider
from collectai.types.enums import LlmMode

_SYNTHETIC_API_KEY = SecretStr("sk-ant-SYNTHETIC-TEST-KEY-not-real")


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "llm_mode": LlmMode.MOCK,
        "anthropic_model": None,
        "anthropic_api_key": None,
        "tool_call_cap_per_turn": 5,
        "ai_retry_bound": 1,
        "max_clarification_turns": 2,
        "chat_rate_limit_per_minute": 20,
        "api_rate_limit_per_minute": 300,
        "provider_timeout_seconds": 20,
        "proposal_ttl_minutes": 30,
        "demo_controls_enabled": False,
        "database_url": "postgresql+asyncpg://collectai:synthetic@localhost:5432/collectai",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_get_provider_returns_mock_provider_in_mock_mode() -> None:
    settings = _settings(llm_mode=LlmMode.MOCK)

    provider = get_provider(settings)

    assert isinstance(provider, MockProvider)


def test_get_provider_returns_anthropic_provider_in_live_mode() -> None:
    settings = _settings(
        llm_mode=LlmMode.LIVE,
        anthropic_model="synthetic-test-model-1",
        anthropic_api_key=_SYNTHETIC_API_KEY,
        provider_timeout_seconds=15,
    )

    provider = get_provider(settings)

    assert isinstance(provider, AnthropicProvider)


def test_get_provider_raises_when_live_mode_is_missing_model() -> None:
    settings = _settings(
        llm_mode=LlmMode.LIVE, anthropic_model=None, anthropic_api_key=_SYNTHETIC_API_KEY
    )

    with pytest.raises(MissingLiveCredentialsError, match="anthropic_model"):
        get_provider(settings)


def test_get_provider_raises_when_live_mode_is_missing_api_key() -> None:
    settings = _settings(
        llm_mode=LlmMode.LIVE, anthropic_model="synthetic-test-model-1", anthropic_api_key=None
    )

    with pytest.raises(MissingLiveCredentialsError, match="anthropic_api_key"):
        get_provider(settings)
