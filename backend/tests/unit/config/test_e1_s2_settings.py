"""Tests for validated application configuration (E1-S2 AC6, AC7).

`load_settings` always takes an explicit environment mapping in these tests
(never `os.environ` implicitly), so a developer's local `.env` can never leak
into test results — see `.claude/skills/code-gen/SKILL.md`'s pydantic-settings
gotcha. `collectai.config.settings` itself never calls `dotenv.load_dotenv`;
it only reads whatever mapping is handed to it (defaulting to `os.environ` in
non-test callers such as `bootstrap/main.py`).
"""

from __future__ import annotations

import pytest

from collectai.config.settings import StartupConfigError, load_settings
from collectai.types.enums import LlmMode

_BASE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://collectai:synthetic@localhost:5432/collectai",
}


def _env(**overrides: str) -> dict[str, str]:
    return {**_BASE_ENV, **overrides}


def test_defaults_apply_when_only_required_keys_are_set() -> None:
    settings = load_settings(_env())

    assert settings.llm_mode == LlmMode.MOCK
    assert settings.tool_call_cap_per_turn == 5
    assert settings.ai_retry_bound == 1
    assert settings.max_clarification_turns == 2
    assert settings.chat_rate_limit_per_minute == 20
    assert settings.api_rate_limit_per_minute == 300
    assert settings.provider_timeout_seconds == 20
    assert settings.proposal_ttl_minutes == 30
    assert settings.demo_controls_enabled is False


def test_reads_model_name_from_anthropic_model_env_var() -> None:
    settings = load_settings(
        _env(
            LLM_MODE="LIVE",
            ANTHROPIC_MODEL="test-model-id",
            ANTHROPIC_API_KEY="sk-ant-TEST-SYNTHETIC-KEY",
        )
    )
    assert settings.anthropic_model == "test-model-id"
    assert settings.llm_mode == LlmMode.LIVE


def test_live_mode_without_model_fails_startup_with_named_error() -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(LLM_MODE="LIVE", ANTHROPIC_API_KEY="sk-ant-TEST-SYNTHETIC-KEY"))
    assert exc_info.value.parameter == "ANTHROPIC_MODEL"


def test_live_mode_without_api_key_fails_startup_with_named_error() -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(LLM_MODE="LIVE", ANTHROPIC_MODEL="test-model-id"))
    assert exc_info.value.parameter == "ANTHROPIC_API_KEY"


def test_missing_database_url_fails_startup_with_named_error() -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings({})
    assert exc_info.value.parameter == "DATABASE_URL"


@pytest.mark.parametrize("invalid_value", ["0", "21"])
def test_tool_call_cap_boundary_violations_fail_startup(invalid_value: str) -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(TOOL_CALL_CAP_PER_TURN=invalid_value))
    assert exc_info.value.parameter == "TOOL_CALL_CAP_PER_TURN"


@pytest.mark.parametrize("valid_value", ["1", "5", "20"])
def test_tool_call_cap_boundary_values_are_accepted(valid_value: str) -> None:
    settings = load_settings(_env(TOOL_CALL_CAP_PER_TURN=valid_value))
    assert settings.tool_call_cap_per_turn == int(valid_value)


@pytest.mark.parametrize("invalid_value", ["-1", "3"])
def test_ai_retry_bound_out_of_range_fails_startup(invalid_value: str) -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(AI_RETRY_BOUND=invalid_value))
    assert exc_info.value.parameter == "AI_RETRY_BOUND"


@pytest.mark.parametrize("invalid_value", ["-1", "6"])
def test_max_clarification_turns_out_of_range_fails_startup(invalid_value: str) -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(MAX_CLARIFICATION_TURNS=invalid_value))
    assert exc_info.value.parameter == "MAX_CLARIFICATION_TURNS"


@pytest.mark.parametrize("invalid_value", ["0", "601"])
def test_chat_rate_limit_out_of_range_fails_startup(invalid_value: str) -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(CHAT_RATE_LIMIT_PER_MINUTE=invalid_value))
    assert exc_info.value.parameter == "CHAT_RATE_LIMIT_PER_MINUTE"


def test_invalid_llm_mode_fails_startup_with_named_error() -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(LLM_MODE="TURBO"))
    assert exc_info.value.parameter == "LLM_MODE"


def test_non_integer_tool_call_cap_fails_startup_with_named_error() -> None:
    with pytest.raises(StartupConfigError) as exc_info:
        load_settings(_env(TOOL_CALL_CAP_PER_TURN="not-a-number"))
    assert exc_info.value.parameter == "TOOL_CALL_CAP_PER_TURN"


def test_demo_controls_enabled_parses_boolean_env_var() -> None:
    settings = load_settings(_env(DEMO_CONTROLS_ENABLED="true"))
    assert settings.demo_controls_enabled is True


def test_anthropic_api_key_never_appears_in_repr() -> None:
    settings = load_settings(
        _env(
            LLM_MODE="LIVE",
            ANTHROPIC_MODEL="test-model-id",
            ANTHROPIC_API_KEY="sk-ant-TEST-SYNTHETIC-KEY",
        )
    )
    assert "sk-ant-TEST-SYNTHETIC-KEY" not in repr(settings)
