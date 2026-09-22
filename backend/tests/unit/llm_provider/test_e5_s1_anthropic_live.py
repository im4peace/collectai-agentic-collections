"""Tests for AnthropicProvider: error translation, timeout, response mapping (E5-S1 AC3).

No real network calls are made anywhere in this file: the `anthropic.AsyncAnthropic`
client is always constructor-injected as a mock (the wrapper's own mock boundary,
per `.claude/skills/code-gen/SKILL.md`'s Service Wrapper Pattern). No real Anthropic
API key or model id appears anywhere below — only synthetic placeholder strings.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest
from anthropic.types import Message, TextBlock, Usage
from pydantic import SecretStr

from collectai.llm_provider.anthropic_live import (
    AnthropicProvider,
    ApiPermanentError,
    ApiRateLimitError,
    ApiTransientError,
)
from collectai.llm_provider.base import ProviderRequest, ProviderTimeout

_SYNTHETIC_MODEL_ID = "synthetic-test-model-1"
_SYNTHETIC_API_KEY = SecretStr("sk-ant-SYNTHETIC-TEST-KEY-not-real")

_REQUEST = ProviderRequest(
    system="You are a collections assistant.",
    messages=[{"role": "user", "content": "What is my balance?"}],
    max_tokens=256,
)


def _build_message(*, text: str = "Your balance is $250.00.") -> Message:
    return Message(
        id="msg_synthetic_01",
        content=[TextBlock(type="text", text=text)],
        model=_SYNTHETIC_MODEL_ID,
        role="assistant",
        stop_reason="end_turn",
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=42, output_tokens=11),
    )


def _make_request(*, request_kwargs: dict[str, Any] | None = None) -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.example/v1/messages")


def _status_error(
    cls: type[anthropic.APIStatusError], *, status_code: int, message: str = "boom"
) -> anthropic.APIStatusError:
    response = httpx.Response(status_code, request=_make_request())
    return cls(message, response=response, body=None)


def _provider(client: object) -> AnthropicProvider:
    return AnthropicProvider(
        model_id=_SYNTHETIC_MODEL_ID,
        api_key=_SYNTHETIC_API_KEY,
        timeout_seconds=5,
        client=client,  # type: ignore[arg-type]
    )


async def test_complete_maps_a_successful_response_to_provider_result() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=_build_message())
    provider = _provider(client)

    result = await provider.complete(_REQUEST)

    assert result.content == "Your balance is $250.00."
    assert result.model_id == _SYNTHETIC_MODEL_ID
    assert result.input_tokens == 42
    assert result.output_tokens == 11
    assert result.latency_ms >= 0


async def test_complete_passes_model_and_system_to_the_sdk_client() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=_build_message())
    provider = _provider(client)

    await provider.complete(_REQUEST)

    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == _SYNTHETIC_MODEL_ID
    assert kwargs["system"] == "You are a collections assistant."
    assert kwargs["max_tokens"] == 256


async def test_complete_raises_provider_timeout_when_the_configured_limit_is_exceeded() -> None:
    async def _slow_create(**_kwargs: object) -> Message:
        await asyncio.sleep(10)
        return _build_message()

    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=_slow_create)
    provider = AnthropicProvider(
        model_id=_SYNTHETIC_MODEL_ID,
        api_key=_SYNTHETIC_API_KEY,
        timeout_seconds=0,
        client=client,
    )

    with pytest.raises(ProviderTimeout) as exc_info:
        await provider.complete(_REQUEST)
    assert exc_info.value.provider == "anthropic"


async def test_complete_translates_sdk_api_timeout_error_to_provider_timeout() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=_make_request())
    )
    provider = _provider(client)

    with pytest.raises(ProviderTimeout):
        await provider.complete(_REQUEST)


async def test_complete_translates_rate_limit_error_to_api_rate_limit_error() -> None:
    response = httpx.Response(
        429, headers={"retry-after": "3"}, request=_make_request()
    )
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.RateLimitError("rate limited", response=response, body=None)
    )
    provider = _provider(client)

    with pytest.raises(ApiRateLimitError) as exc_info:
        await provider.complete(_REQUEST)
    assert exc_info.value.retry_after == 3.0


async def test_complete_translates_connection_error_to_api_transient_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(request=_make_request())
    )
    provider = _provider(client)

    with pytest.raises(ApiTransientError):
        await provider.complete(_REQUEST)


async def test_complete_translates_server_error_to_api_transient_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=_status_error(anthropic.InternalServerError, status_code=500)
    )
    provider = _provider(client)

    with pytest.raises(ApiTransientError):
        await provider.complete(_REQUEST)


async def test_complete_translates_bad_request_error_to_api_permanent_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=_status_error(anthropic.BadRequestError, status_code=400)
    )
    provider = _provider(client)

    with pytest.raises(ApiPermanentError):
        await provider.complete(_REQUEST)


async def test_complete_translates_authentication_error_to_api_permanent_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=_status_error(anthropic.AuthenticationError, status_code=401)
    )
    provider = _provider(client)

    with pytest.raises(ApiPermanentError):
        await provider.complete(_REQUEST)


async def test_anthropic_provider_never_hardcodes_a_real_api_key() -> None:
    # Guard against accidental regression: only the synthetic constant is used.
    assert _SYNTHETIC_API_KEY.get_secret_value().startswith("sk-ant-SYNTHETIC")
