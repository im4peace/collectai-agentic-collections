"""Shared types for the fail-closed AI write path (E5-S2 AC6).

Split out of `orchestrator.py` to keep that module under the code-gen
skill's 300-line block threshold: this module owns the *shapes*
(`AiCallContext`, `AiInteractionResult`) and the audit-metadata bookkeeping
(`_CallAccumulator`, `_Accounting`); `orchestrator.py` and
`_interaction_outcomes.py` both depend on it, never each other's internals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Generic, Literal, TypedDict, TypeVar

from pydantic import BaseModel

from collectai.ai_orchestration.ports import DomainWriteOutcome
from collectai.audit.service import AuditService
from collectai.llm_provider.base import ProviderResult
from collectai.types.enums import Persona, ProviderMode, SafeState

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AiInteractionMetadataKwargs(TypedDict):
    """Exactly the keyword arguments `audit.events.build_ai_interaction_draft`
    expects for the fields `Accounting.metadata_kwargs` computes (AC6),
    typed so `**accounting.metadata_kwargs()` type-checks at every call
    site instead of unpacking a bare `dict[str, object]`."""

    correlation_id: str
    capability: str
    provider: str
    provider_mode: ProviderMode
    prompt_version: str
    actor_persona: Persona | None
    customer_id: str | None
    account_id: str | None
    model_id: str | None
    policy_version: str | None
    latency: dict[str, object]
    token_usage: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class AiCallContext:
    """Everything about *this* AI call that goes into its audit event but
    is not the call's content (AC6)."""

    correlation_id: str
    capability: str
    prompt_version: str
    provider_name: str
    provider_mode: ProviderMode
    policy_version: str | None = None
    actor_persona: Persona | None = None
    customer_id: str | None = None
    account_id: str | None = None


@dataclass(frozen=True, slots=True)
class AiInteractionResult(Generic[SchemaT]):
    """The outcome of one `orchestrator.run_ai_interaction` call.

    `model_id` (E4-S3): the id of the model that actually produced
    `structured_output`, read back from `CallAccumulator.last_model_id` --
    exposed here because an advisory caller that persists its own governed
    record (e.g. a stored `Recommendation`) needs to know which model
    produced it, not just that *some* provider call happened. `None` when no
    provider call ever returned a usable result.

    `unavailable_reason` (E4-S3): distinguishes the two `SafeState
    .AI_UNAVAILABLE` outcomes an advisory caller must treat differently per
    api-contracts.md 3.5 ("AI failure" vs. "schema-invalid output after one
    retry") -- `run_ai_interaction` itself never exposed which one occurred
    before this field existed. `None` for every other outcome."""

    safe_state: SafeState
    structured_output: SchemaT | None
    domain_outcome: DomainWriteOutcome | None
    offer_handoff: bool
    governed: bool
    model_id: str | None = None
    unavailable_reason: Literal["PROVIDER_TIMEOUT", "SCHEMA_INVALID"] | None = None


@dataclass(slots=True)
class CallAccumulator:
    """Provider calls actually made during one interaction, for AC6's
    latency/token accounting across however many attempts it took."""

    results: list[ProviderResult] = field(default_factory=list)

    def add(self, result: ProviderResult) -> None:
        self.results.append(result)

    @property
    def provider_latency_ms(self) -> float:
        return sum(result.latency_ms for result in self.results)

    @property
    def input_tokens(self) -> int | None:
        values = [r.input_tokens for r in self.results if r.input_tokens is not None]
        return sum(values) if values else None

    @property
    def output_tokens(self) -> int | None:
        values = [r.output_tokens for r in self.results if r.output_tokens is not None]
        return sum(values) if values else None

    @property
    def last_model_id(self) -> str | None:
        return self.results[-1].model_id if self.results else None


@dataclass(frozen=True, slots=True)
class Accounting:
    """Everything a `_finish_*` helper needs to build and record this
    interaction's audit event, bundled so `run_ai_interaction` does not pass
    five loose parameters to each one."""

    audit_service: AuditService
    context: AiCallContext
    accumulator: CallAccumulator
    started_at: float
    tool_call_duration_ms: float | None

    def metadata_kwargs(self) -> AiInteractionMetadataKwargs:
        elapsed_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        latency: dict[str, object] = {
            "provider_latency_ms": round(self.accumulator.provider_latency_ms, 2),
            "interaction_duration_ms": elapsed_ms,
        }
        if self.tool_call_duration_ms is not None:
            latency["tool_call_duration_ms"] = self.tool_call_duration_ms
        input_tokens = self.accumulator.input_tokens
        output_tokens = self.accumulator.output_tokens
        token_usage: dict[str, object] | None = None
        if input_tokens is not None or output_tokens is not None:
            token_usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        return {
            "correlation_id": self.context.correlation_id,
            "capability": self.context.capability,
            "provider": self.context.provider_name,
            "provider_mode": self.context.provider_mode,
            "prompt_version": self.context.prompt_version,
            "actor_persona": self.context.actor_persona,
            "customer_id": self.context.customer_id,
            "account_id": self.context.account_id,
            "model_id": self.accumulator.last_model_id,
            "policy_version": self.context.policy_version,
            "latency": latency,
            "token_usage": token_usage,
        }
