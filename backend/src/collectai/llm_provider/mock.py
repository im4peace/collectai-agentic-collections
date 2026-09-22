"""Scriptable MockProvider — zero network calls, ever (E5-S1 AC1, AC2)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Final

from collectai.llm_provider.base import ProviderRequest, ProviderResult

_DEFAULT_MODEL_ID: Final[str] = "mock-model-1"


class MockProviderExhaustedError(Exception):
    """Raised when `MockProvider.complete()` is called with no scripts left."""

    def __init__(self, *, calls_made: int) -> None:
        self.calls_made = calls_made
        super().__init__(
            f"MockProvider exhausted its scripted responses after {calls_made} call(s)."
        )


class MockProvider:
    """Deterministic, network-free `LlmProvider` for tests and demos.

    Construct with a sequence of scripted outcomes consumed in order, one per
    `complete()` call. Each outcome is either a `ProviderResult` (returned
    as-is — valid, malformed or adversarial; this class never inspects or
    judges `content`, only replays what it is told) or an `Exception`
    instance (raised as-is, e.g. a pre-built `ProviderTimeout` to script a
    timeout deterministically without sleeping). When `responses` is omitted,
    every call returns a single fixed valid `ProviderResult`.
    """

    def __init__(self, responses: Iterable[ProviderResult | Exception] | None = None) -> None:
        self._queue: deque[ProviderResult | Exception] | None = (
            deque(responses) if responses is not None else None
        )
        self._calls_made = 0

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        del request  # MockProvider never inspects the request; it only replays scripts.
        self._calls_made += 1
        if self._queue is None:
            return _default_response()
        if not self._queue:
            raise MockProviderExhaustedError(calls_made=self._calls_made)
        outcome = self._queue.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _default_response() -> ProviderResult:
    return ProviderResult(
        content="Acknowledged.",
        model_id=_DEFAULT_MODEL_ID,
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
    )
