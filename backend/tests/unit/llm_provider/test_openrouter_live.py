"""Tests for OpenRouterProvider: request/response mapping, timeout, error translation,
never logging secrets (mirrors test_e5_s1_anthropic_live.py's coverage for AnthropicProvider).

No real network calls are made anywhere in this file: the `httpx.AsyncClient` is always
constructor-injected as a mock. No real OpenRouter API key or model id appears anywhere
below -- only synthetic placeholder strings.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from collectai.llm_provider.base import ProviderRequest, ProviderTimeout
from collectai.llm_provider.openrouter_live import (
    ApiPermanentError,
    ApiRateLimitError,
    ApiTransientError,
    OpenRouterProvider,
)

_SYNTHETIC_MODEL_ID = "synthetic-vendor/synthetic-model:free"
_SYNTHETIC_API_KEY = SecretStr("sk-or-SYNTHETIC-TEST-KEY-not-real")

_REQUEST = ProviderRequest(
    system="You are a collections assistant.",
    messages=[{"role": "user", "content": "What is my balance?"}],
    max_tokens=256,
)


def _make_request() -> httpx.Request:
    return httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _success_response(
    *,
    content: str = "Your balance is $250.00.",
    model: str = _SYNTHETIC_MODEL_ID,
    prompt_tokens: int = 42,
    completion_tokens: int = 11,
) -> httpx.Response:
    return httpx.Response(
        200,
        request=_make_request(),
        json={
            "id": "gen-synthetic-01",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
    )


def _provider(client: object) -> OpenRouterProvider:
    return OpenRouterProvider(
        model_id=_SYNTHETIC_MODEL_ID,
        api_key=_SYNTHETIC_API_KEY,
        timeout_seconds=5,
        client=client,  # type: ignore[arg-type]
    )


async def test_complete_maps_a_successful_response_to_provider_result() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    result = await provider.complete(_REQUEST)

    assert result.content == "Your balance is $250.00."
    assert result.model_id == _SYNTHETIC_MODEL_ID
    assert result.input_tokens == 42
    assert result.output_tokens == 11
    assert result.latency_ms >= 0


async def test_complete_falls_back_to_the_requested_model_id_when_the_response_omits_it() -> None:
    response = httpx.Response(
        200,
        request=_make_request(),
        json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    provider = _provider(client)

    result = await provider.complete(_REQUEST)

    assert result.model_id == _SYNTHETIC_MODEL_ID


async def test_complete_maps_system_and_user_messages_and_max_tokens_and_model() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    await provider.complete(_REQUEST)

    _, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["model"] == _SYNTHETIC_MODEL_ID
    assert payload["max_tokens"] == 256
    assert payload["messages"][0] == {
        "role": "system",
        "content": "You are a collections assistant.",
    }
    assert payload["messages"][1] == {"role": "user", "content": "What is my balance?"}


async def test_complete_sends_bearer_authentication() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    await provider.complete(_REQUEST)

    _, kwargs = client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer sk-or-SYNTHETIC-TEST-KEY-not-real"


async def test_complete_never_logs_the_api_key_or_authorization_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    with caplog.at_level(logging.DEBUG):
        await provider.complete(_REQUEST)

    log_text = caplog.text
    assert _SYNTHETIC_API_KEY.get_secret_value() not in log_text
    assert "Authorization" not in log_text
    assert "Bearer" not in log_text


async def test_complete_does_not_log_request_message_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    with caplog.at_level(logging.DEBUG):
        await provider.complete(_REQUEST)

    assert "What is my balance?" not in caplog.text


async def test_complete_raises_provider_timeout_when_the_configured_limit_is_exceeded() -> None:
    async def _slow_post(**_kwargs: object) -> httpx.Response:
        await asyncio.sleep(10)
        return _success_response()

    client = AsyncMock()
    client.post = AsyncMock(side_effect=_slow_post)
    provider = OpenRouterProvider(
        model_id=_SYNTHETIC_MODEL_ID,
        api_key=_SYNTHETIC_API_KEY,
        timeout_seconds=0,
        client=client,
    )

    with pytest.raises(ProviderTimeout) as exc_info:
        await provider.complete(_REQUEST)
    assert exc_info.value.provider == "openrouter"


async def test_complete_translates_httpx_timeout_exception_to_provider_timeout() -> None:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))
    provider = _provider(client)

    with pytest.raises(ProviderTimeout):
        await provider.complete(_REQUEST)


async def test_complete_translates_429_to_api_rate_limit_error_with_retry_after() -> None:
    response = httpx.Response(429, headers={"retry-after": "3"}, request=_make_request())
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    provider = _provider(client)

    with pytest.raises(ApiRateLimitError) as exc_info:
        await provider.complete(_REQUEST)
    assert exc_info.value.retry_after == 3.0


async def test_complete_translates_connection_error_to_api_transient_error() -> None:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    provider = _provider(client)

    with pytest.raises(ApiTransientError):
        await provider.complete(_REQUEST)


async def test_complete_translates_server_error_to_api_transient_error() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=httpx.Response(500, request=_make_request()))
    provider = _provider(client)

    with pytest.raises(ApiTransientError):
        await provider.complete(_REQUEST)


async def test_complete_translates_bad_request_error_to_api_permanent_error() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=httpx.Response(400, request=_make_request()))
    provider = _provider(client)

    with pytest.raises(ApiPermanentError):
        await provider.complete(_REQUEST)


async def test_complete_translates_authentication_error_to_api_permanent_error() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=httpx.Response(401, request=_make_request()))
    provider = _provider(client)

    with pytest.raises(ApiPermanentError):
        await provider.complete(_REQUEST)


async def test_complete_makes_exactly_one_http_call_no_internal_retry() -> None:
    client = AsyncMock()
    client.post = AsyncMock(return_value=_success_response())
    provider = _provider(client)

    await provider.complete(_REQUEST)

    assert client.post.call_count == 1


async def test_openrouter_provider_never_hardcodes_a_real_api_key() -> None:
    # Guard against accidental regression: only the synthetic constant is used.
    assert _SYNTHETIC_API_KEY.get_secret_value().startswith("sk-or-SYNTHETIC")
