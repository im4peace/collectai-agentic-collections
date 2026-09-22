"""AnthropicProvider — the only module anywhere allowed to import `anthropic`.

Wraps `anthropic.AsyncAnthropic` behind the `LlmProvider` protocol (Service
Wrapper Pattern, `.claude/skills/code-gen/SKILL.md`): business/orchestration
code never sees the SDK's request or response objects, only `ProviderResult`.
The SDK client is constructor-injected, never a module-level singleton, so
tests exercise error translation, timeout handling and response mapping by
injecting a mock client — no real network access and no real API key are
used anywhere in this file or its tests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Final, cast

import anthropic
from anthropic.types import Message, MessageParam, TextBlock
from pydantic import SecretStr

from collectai.llm_provider.base import ProviderRequest, ProviderResult, ProviderTimeout

logger = logging.getLogger(__name__)

_PROVIDER_NAME: Final[str] = "anthropic"


class ApiTransientError(Exception):
    """Retryable failure: connection error, 5xx status, overloaded."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ApiPermanentError(Exception):
    """Non-retryable failure: 4xx status, auth failure, malformed request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ApiRateLimitError(ApiTransientError):
    """Rate limited (HTTP 429), optionally with a retry-after hint in seconds."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class AnthropicProvider:
    """`LlmProvider` implementation backed by the real Anthropic API (LIVE mode)."""

    def __init__(
        self,
        *,
        model_id: str,
        api_key: SecretStr,
        timeout_seconds: int,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._model_id = model_id
        self._timeout_seconds = timeout_seconds
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key.get_secret_value(), timeout=float(timeout_seconds)
        )

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        start = time.monotonic()
        response = await self._call_sdk(request)
        latency_ms = (time.monotonic() - start) * 1000
        result = _to_provider_result(response, latency_ms=latency_ms)
        _log_raw_response(response, result=result)
        return result

    async def _call_sdk(self, request: ProviderRequest) -> Message:
        try:
            return await asyncio.wait_for(
                self._create_message(request), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            raise ProviderTimeout(
                provider=_PROVIDER_NAME, timeout_seconds=self._timeout_seconds
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeout(
                provider=_PROVIDER_NAME, timeout_seconds=self._timeout_seconds
            ) from exc
        except anthropic.RateLimitError as exc:
            raise _translate_rate_limit_error(exc) from exc
        except anthropic.APIConnectionError as exc:
            raise ApiTransientError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise _translate_status_error(exc) from exc
        except anthropic.APIError as exc:
            raise ApiTransientError(str(exc)) from exc
        except anthropic.AnthropicError as exc:
            raise ApiPermanentError(str(exc)) from exc

    async def _create_message(self, request: ProviderRequest) -> Message:
        messages = cast(list[MessageParam], request.messages)
        if request.system is not None:
            return await self._client.messages.create(
                model=self._model_id,
                max_tokens=request.max_tokens,
                messages=messages,
                system=request.system,
            )
        return await self._client.messages.create(
            model=self._model_id,
            max_tokens=request.max_tokens,
            messages=messages,
        )


def _translate_status_error(
    exc: anthropic.APIStatusError,
) -> ApiTransientError | ApiPermanentError:
    if exc.status_code >= 500:
        return ApiTransientError(str(exc), status_code=exc.status_code)
    return ApiPermanentError(str(exc), status_code=exc.status_code)


def _translate_rate_limit_error(exc: anthropic.RateLimitError) -> ApiRateLimitError:
    return ApiRateLimitError(str(exc), retry_after=_parse_retry_after(exc))


def _parse_retry_after(exc: anthropic.RateLimitError) -> float | None:
    header_value = exc.response.headers.get("retry-after")
    if header_value is None:
        return None
    try:
        return float(header_value)
    except ValueError:
        return None


def _to_provider_result(response: Message, *, latency_ms: float) -> ProviderResult:
    usage = response.usage
    return ProviderResult(
        content=_extract_text(response),
        model_id=response.model,
        latency_ms=latency_ms,
        input_tokens=usage.input_tokens if usage is not None else None,
        output_tokens=usage.output_tokens if usage is not None else None,
    )


def _extract_text(response: Message) -> str:
    return "".join(block.text for block in response.content if isinstance(block, TextBlock))


def _log_raw_response(response: Message, *, result: ProviderResult) -> None:
    logger.debug(
        "Anthropic response received",
        extra={
            "provider": _PROVIDER_NAME,
            "model_id": result.model_id,
            "latency_ms": round(result.latency_ms, 2),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "stop_reason": response.stop_reason,
            "raw_content": str(response.content)[:1000],
        },
    )
