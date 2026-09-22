"""Validated application configuration (specs/policy-ruleset-contract.md section 4).

Every key is validated at `load_settings()` call time, never lazily re-checked
by callers. An invalid or missing required value raises `StartupConfigError`,
a named error identifying exactly which key failed and why.

`load_settings` takes an explicit environment mapping (defaulting to
`os.environ` only when the caller passes none). It never calls
`dotenv.load_dotenv` and does not depend on `pydantic-settings`, so tests that
always pass an explicit mapping are fully isolated from whatever is in a
developer's local `.env` file (see `.claude/skills/code-gen/SKILL.md`'s
pydantic-settings gotcha) — there is simply no `.env`-reading code path to
trigger.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from collectai.types.enums import LlmMode

logger = logging.getLogger(__name__)

_TOOL_CALL_CAP_RANGE: Final[tuple[int, int]] = (1, 20)
_AI_RETRY_BOUND_RANGE: Final[tuple[int, int]] = (0, 2)
_MAX_CLARIFICATION_TURNS_RANGE: Final[tuple[int, int]] = (0, 5)
_CHAT_RATE_LIMIT_RANGE: Final[tuple[int, int]] = (1, 600)
_API_RATE_LIMIT_RANGE: Final[tuple[int, int]] = (1, 6000)
_PROVIDER_TIMEOUT_RANGE: Final[tuple[int, int]] = (1, 120)
_PROPOSAL_TTL_RANGE: Final[tuple[int, int]] = (1, 1440)

_TRUE_VALUES: Final[frozenset[str]] = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES: Final[frozenset[str]] = frozenset({"false", "0", "no", "off"})


class StartupConfigError(Exception):
    """Raised when a configuration key is missing or fails its contract range."""

    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"Invalid configuration for '{parameter}': {reason}")


class Settings(BaseModel):
    """Validated application configuration. Never carries a hard-coded secret."""

    model_config = ConfigDict(frozen=True)

    llm_mode: LlmMode
    anthropic_model: str | None
    anthropic_api_key: SecretStr | None
    tool_call_cap_per_turn: int
    ai_retry_bound: int
    max_clarification_turns: int
    chat_rate_limit_per_minute: int
    api_rate_limit_per_minute: int
    provider_timeout_seconds: int
    proposal_ttl_minutes: int
    demo_controls_enabled: bool
    database_url: str


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Validate and build `Settings` from an environment mapping.

    Defaults to `os.environ` when `env` is omitted. Raises `StartupConfigError`
    naming the first invalid or missing key found.
    """
    source = env if env is not None else os.environ

    llm_mode = _read_llm_mode(source)
    anthropic_model = source.get("ANTHROPIC_MODEL") or None
    anthropic_api_key_raw = source.get("ANTHROPIC_API_KEY") or None
    _require_live_mode_credentials(llm_mode, anthropic_model, anthropic_api_key_raw)

    try:
        settings = Settings(
            llm_mode=llm_mode,
            anthropic_model=anthropic_model,
            anthropic_api_key=SecretStr(anthropic_api_key_raw) if anthropic_api_key_raw else None,
            tool_call_cap_per_turn=_read_int_in_range(
                "TOOL_CALL_CAP_PER_TURN", source, default=5, bounds=_TOOL_CALL_CAP_RANGE
            ),
            ai_retry_bound=_read_int_in_range(
                "AI_RETRY_BOUND", source, default=1, bounds=_AI_RETRY_BOUND_RANGE
            ),
            max_clarification_turns=_read_int_in_range(
                "MAX_CLARIFICATION_TURNS",
                source,
                default=2,
                bounds=_MAX_CLARIFICATION_TURNS_RANGE,
            ),
            chat_rate_limit_per_minute=_read_int_in_range(
                "CHAT_RATE_LIMIT_PER_MINUTE", source, default=20, bounds=_CHAT_RATE_LIMIT_RANGE
            ),
            api_rate_limit_per_minute=_read_int_in_range(
                "API_RATE_LIMIT_PER_MINUTE", source, default=300, bounds=_API_RATE_LIMIT_RANGE
            ),
            provider_timeout_seconds=_read_int_in_range(
                "PROVIDER_TIMEOUT_SECONDS", source, default=20, bounds=_PROVIDER_TIMEOUT_RANGE
            ),
            proposal_ttl_minutes=_read_int_in_range(
                "PROPOSAL_TTL_MINUTES", source, default=30, bounds=_PROPOSAL_TTL_RANGE
            ),
            demo_controls_enabled=_read_bool("DEMO_CONTROLS_ENABLED", source, default=False),
            database_url=_require_str("DATABASE_URL", source),
        )
    except ValidationError as exc:
        first_error = exc.errors()[0]
        parameter = ".".join(str(part) for part in first_error["loc"]) or "<settings>"
        raise StartupConfigError(parameter=parameter, reason=first_error["msg"]) from exc

    logger.info(
        "Application configuration validated",
        extra={"llm_mode": llm_mode.value, "demo_controls_enabled": settings.demo_controls_enabled},
    )
    return settings


def _read_llm_mode(env: Mapping[str, str]) -> LlmMode:
    raw = env.get("LLM_MODE")
    if raw is None:
        return LlmMode.MOCK
    try:
        return LlmMode(raw)
    except ValueError as exc:
        allowed = [member.value for member in LlmMode]
        raise StartupConfigError(
            parameter="LLM_MODE", reason=f"must be one of {allowed}, got {raw!r}"
        ) from exc


def _require_live_mode_credentials(
    llm_mode: LlmMode, anthropic_model: str | None, anthropic_api_key: str | None
) -> None:
    if llm_mode is not LlmMode.LIVE:
        return
    if not anthropic_model:
        raise StartupConfigError(
            parameter="ANTHROPIC_MODEL", reason="required when LLM_MODE=LIVE"
        )
    if not anthropic_api_key:
        raise StartupConfigError(
            parameter="ANTHROPIC_API_KEY", reason="required when LLM_MODE=LIVE"
        )


def _read_int_in_range(
    key: str, env: Mapping[str, str], *, default: int, bounds: tuple[int, int]
) -> int:
    raw = env.get(key)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise StartupConfigError(
                parameter=key, reason=f"must be an integer, got {raw!r}"
            ) from exc
    low, high = bounds
    if not (low <= value <= high):
        raise StartupConfigError(
            parameter=key, reason=f"must be between {low} and {high}, got {value}"
        )
    return value


def _read_bool(key: str, env: Mapping[str, str], *, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise StartupConfigError(
        parameter=key, reason=f"must be a boolean (true/false/1/0/yes/no/on/off), got {raw!r}"
    )


def _require_str(key: str, env: Mapping[str, str]) -> str:
    raw = env.get(key)
    if not raw:
        raise StartupConfigError(parameter=key, reason="is required")
    return raw
