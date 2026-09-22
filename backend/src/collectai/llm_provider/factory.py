"""Provider selection by configuration — the one place mode is chosen (E5-S1 AC1)."""

from __future__ import annotations

from collectai.config.settings import Settings
from collectai.llm_provider.anthropic_live import AnthropicProvider
from collectai.llm_provider.base import LlmProvider
from collectai.llm_provider.mock import MockProvider
from collectai.types.enums import LlmMode


class MissingLiveCredentialsError(Exception):
    """Raised when `Settings.llm_mode` is LIVE but a required field is unset.

    `load_settings()` already enforces this at startup, so this should be
    unreachable in practice; it exists as a fail-fast guard for any caller
    that constructs `Settings` directly (e.g. in tests) without going through
    `load_settings()`.
    """

    def __init__(self, *, parameter: str) -> None:
        self.parameter = parameter
        super().__init__(f"LIVE mode requires '{parameter}' to be set on Settings.")


def get_provider(settings: Settings) -> LlmProvider:
    """Return the `LlmProvider` selected by `settings.llm_mode`.

    Reads only `settings.llm_mode` (and, for LIVE, the already-validated
    `anthropic_model` / `anthropic_api_key` / `provider_timeout_seconds`
    fields) — never an environment variable directly. `load_settings()` is
    solely responsible for reading and validating environment variables.
    """
    if settings.llm_mode is LlmMode.MOCK:
        return MockProvider()
    return _build_anthropic_provider(settings)


def _build_anthropic_provider(settings: Settings) -> AnthropicProvider:
    if settings.anthropic_model is None:
        raise MissingLiveCredentialsError(parameter="anthropic_model")
    if settings.anthropic_api_key is None:
        raise MissingLiveCredentialsError(parameter="anthropic_api_key")
    return AnthropicProvider(
        model_id=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        timeout_seconds=settings.provider_timeout_seconds,
    )
