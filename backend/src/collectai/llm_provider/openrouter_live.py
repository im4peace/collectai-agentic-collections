"""OpenRouterProvider — httpx-based `LlmProvider` for OpenRouter's OpenAI-
compatible chat-completions API.

Scope: `collectai_eval`'s LIVE evaluation runner only (see
`collectai_eval.runner._build_openrouter_provider`), never the server-side
`llm_provider.factory` / application chat runtime. Mirrors
`anthropic_live.AnthropicProvider`'s shape (constructor-injected client, same
transient/permanent/rate-limit exception taxonomy, single attempt per
`complete()` call with no internal retry loop) so both providers satisfy the
`LlmProvider` protocol identically from the runner's point of view.

Free-tier-only by construction: `collectai_eval.runner._build_openrouter_provider`
refuses to construct this class unless the configured model id ends in
":free" (`LiveEvalOpenRouterModelNotFreeError`) -- this file does not
re-check that guard itself.

The HTTP client is constructor-injected, never a module-level singleton, so
tests exercise error translation, timeout handling and response mapping by
injecting a fake `httpx.AsyncClient` (via `httpx.MockTransport`) -- no real
network access and no real API key are used anywhere in this file or its
tests. Never logs the Authorization header, the API key, or request/response
message content.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Final, cast

import httpx
from pydantic import SecretStr

from collectai.llm_provider.base import ProviderRequest, ProviderResult, ProviderTimeout

logger = logging.getLogger(__name__)

_PROVIDER_NAME: Final[str] = "openrouter"
_DEFAULT_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
_CHAT_COMPLETIONS_PATH: Final[str] = "/chat/completions"


class ApiTransientError(Exception):
    """Retryable failure: connection error, 5xx status."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ApiPermanentError(Exception):
    """Non-retryable failure: 4xx status (other than 429), malformed request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ApiRateLimitError(ApiTransientError):
    """Rate limited (HTTP 429), optionally with a retry-after hint in seconds."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class OpenRouterProvider:
    """`LlmProvider` implementation backed by OpenRouter's chat-completions API."""

    def __init__(
        self,
        *,
        model_id: str,
        api_key: SecretStr,
        timeout_seconds: int,
        client: httpx.AsyncClient | None = None,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self._model_id = model_id
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url
        self._client = client or httpx.AsyncClient(timeout=float(timeout_seconds))

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        start = time.monotonic()
        response_json = await self._call_api(request)
        latency_ms = (time.monotonic() - start) * 1000
        result = _to_provider_result(
            response_json, latency_ms=latency_ms, requested_model_id=self._model_id
        )
        _log_response_metadata(result)
        return result

    async def _call_api(self, request: ProviderRequest) -> dict[str, Any]:
        payload = _to_openrouter_payload(request, model_id=self._model_id)
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        try:
            response = await asyncio.wait_for(
                self._client.post(
                    f"{self._base_url}{_CHAT_COMPLETIONS_PATH}",
                    json=payload,
                    headers=headers,
                ),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeout(
                provider=_PROVIDER_NAME, timeout_seconds=self._timeout_seconds
            ) from exc
        except httpx.HTTPError as exc:
            raise ApiTransientError(str(exc)) from exc

        if response.status_code == 429:
            raise _translate_rate_limit_error(response)
        if response.status_code >= 500:
            raise ApiTransientError(
                f"OpenRouter returned status {response.status_code}",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ApiPermanentError(
                f"OpenRouter returned status {response.status_code}",
                status_code=response.status_code,
            )
        return cast(dict[str, Any], response.json())


def _to_openrouter_payload(request: ProviderRequest, *, model_id: str) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if request.system is not None:
        messages.append({"role": "system", "content": request.system})
    messages.extend(request.messages)
    return {
        "model": model_id,
        "messages": messages,
        "max_tokens": request.max_tokens,
    }


def _translate_rate_limit_error(response: httpx.Response) -> ApiRateLimitError:
    return ApiRateLimitError(
        f"OpenRouter returned status {response.status_code}",
        retry_after=_parse_retry_after(response),
    )


def _parse_retry_after(response: httpx.Response) -> float | None:
    header_value = response.headers.get("retry-after")
    if header_value is None:
        return None
    try:
        return float(header_value)
    except ValueError:
        return None


def _to_provider_result(
    response_json: dict[str, Any], *, latency_ms: float, requested_model_id: str
) -> ProviderResult:
    choices = response_json.get("choices") or []
    content = ""
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
    usage = response_json.get("usage") or {}
    model_id = response_json.get("model") or requested_model_id
    return ProviderResult(
        content=content,
        model_id=model_id,
        latency_ms=latency_ms,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )


def _log_response_metadata(result: ProviderResult) -> None:
    """Logs metadata only -- never request/response message content, the
    Authorization header, or the API key."""
    logger.debug(
        "OpenRouter response received",
        extra={
            "provider": _PROVIDER_NAME,
            "model_id": result.model_id,
            "latency_ms": round(result.latency_ms, 2),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        },
    )
