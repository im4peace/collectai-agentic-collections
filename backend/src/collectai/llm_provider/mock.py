"""Scriptable MockProvider — zero network calls, ever (E5-S1 AC1, AC2)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from collectai.llm_provider import _mock_classifier
from collectai.llm_provider.base import ProviderRequest, ProviderResult


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
    judges `content` when explicit `responses` are given, only replays what
    it is told) or an `Exception` instance (raised as-is, e.g. a pre-built
    `ProviderTimeout` to script a timeout deterministically without
    sleeping). When `responses` is omitted (the exact construction
    `llm_provider.factory.get_provider` uses for every real `LLM_MODE=MOCK`
    server), each call instead goes through `_mock_classifier.classify`,
    which pattern-matches the request and returns real, schema-valid
    structured output for phrasing it recognizes (Group J: E11-S1, E11-S2),
    falling back to the same fixed non-JSON `"Acknowledged."` response as
    before for anything it does not.
    """

    def __init__(self, responses: Iterable[ProviderResult | Exception] | None = None) -> None:
        self._queue: deque[ProviderResult | Exception] | None = (
            deque(responses) if responses is not None else None
        )
        self._calls_made = 0

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        self._calls_made += 1
        if self._queue is None:
            return _mock_classifier.classify(request)
        if not self._queue:
            raise MockProviderExhaustedError(calls_made=self._calls_made)
        outcome = self._queue.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
