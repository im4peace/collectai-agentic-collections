"""LlmProvider contract: request/result shapes, timeout error, protocol.

This module defines the boundary between `ai_orchestration` (a later story)
and the two provider implementations (`mock.py`, `anthropic_live.py`). It is
intentionally minimal: `ProviderResult.content` carries the raw model output
(str, or a dict for already-JSON-decoded output) with no schema validation —
structured-output validation against a typed schema is a later
`ai_orchestration` story's responsibility (see `.claude/skills/code-gen/SKILL.md`,
LLM Integration section), not this one.

No other package may import the `anthropic` SDK; only `anthropic_live.py` may.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

# Matches AuditEvent.model_id's bound in data-models.md (max 120) — the same
# logical value (a model identifier) is stored there, so it gets the same cap
# here per the learned-rules.md "bound consistency" rule.
_MODEL_ID_MAX_LENGTH = 120


class ProviderRequest(BaseModel):
    """A minimal request to an `LlmProvider`.

    Deliberately narrow: no tool-definition plumbing (that is E5-S4's job).
    `messages` is a list of `{"role": ..., "content": ...}` pairs.
    """

    model_config = ConfigDict(frozen=True)

    system: str | None = None
    messages: list[dict[str, str]] = Field(min_length=1)
    max_tokens: int = Field(gt=0)


class ProviderResult(BaseModel):
    """What a provider call returned, independent of MOCK vs LIVE."""

    model_config = ConfigDict(frozen=True)

    content: str | dict[str, object]
    model_id: str = Field(min_length=1, max_length=_MODEL_ID_MAX_LENGTH)
    latency_ms: float = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderTimeout(Exception):
    """Raised when a provider call exceeds its configured timeout."""

    def __init__(self, *, provider: str, timeout_seconds: float) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Provider '{provider}' call exceeded the configured "
            f"{timeout_seconds}s timeout."
        )


@runtime_checkable
class LlmProvider(Protocol):
    """Anything that can complete a `ProviderRequest` (MOCK or LIVE)."""

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """Return a `ProviderResult`, or raise `ProviderTimeout` on timeout."""
        ...
