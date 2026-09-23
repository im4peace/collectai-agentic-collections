"""The fail-closed AI write path (E5-S2; BRD 10.3, 13.1 rows 1, 9, 18):

    LLM -> structured output (Pydantic) -> schema validation ->
    authorization/policy validation -> deterministic domain service ->
    permitted state transition -> append-only audit event.

`run_ai_interaction` is the single entry point. Any invalid or unauthorized
AI output fails closed here: a safe response or human-handoff offer, with
no state change (AC1, AC2, AC4). A validated proposal that the deterministic
domain layer rejects is likewise never presented as applied (AC3) -- the
rule result prevails and a policy-conflict audit event is written.

The audit-metadata bookkeeping (`_interaction_types.py`) and the terminal
outcomes (`_interaction_outcomes.py`) are split into their own modules to
keep this one under the code-gen skill's 300-line block threshold; this
module owns only the provider-call and schema-validation retry sequencing
(AC1, AC2) and re-exports the public types callers need.
"""

from __future__ import annotations

import time

from collectai.ai_orchestration._interaction_outcomes import (
    finish_advisory,
    finish_domain_write,
    finish_invalid_output,
    finish_provider_unavailable,
)
from collectai.ai_orchestration._interaction_types import (
    Accounting,
    AiCallContext,
    AiInteractionResult,
    CallAccumulator,
    SchemaT,
)
from collectai.ai_orchestration.ports import DomainWritePort
from collectai.ai_orchestration.structured_output import (
    StructuredOutputError,
    validate_structured_output,
)
from collectai.audit.service import AuditService
from collectai.llm_provider.base import (
    LlmProvider,
    ProviderRequest,
    ProviderResult,
    ProviderTimeout,
)

__all__ = ["AiCallContext", "AiInteractionResult", "run_ai_interaction"]


async def run_ai_interaction(
    provider: LlmProvider,
    request: ProviderRequest,
    schema: type[SchemaT],
    context: AiCallContext,
    audit_service: AuditService,
    *,
    domain_port: DomainWritePort[SchemaT] | None = None,
    retry_bound: int = 1,
    tool_call_duration_ms: float | None = None,
) -> AiInteractionResult[SchemaT]:
    """Run the fail-closed write path once. `retry_bound` (default 1, the
    BRD 13.1 "standing parameter") bounds both the provider-timeout retry
    (AC2) and the malformed-output correction retry (AC1) independently."""
    accumulator = CallAccumulator()
    accounting = Accounting(
        audit_service, context, accumulator, time.perf_counter(), tool_call_duration_ms
    )

    first_result = await _call_with_timeout_retry(provider, request, retry_bound, accumulator)
    if first_result is None:
        return await finish_provider_unavailable(accounting)

    structured_output = await _validate_with_correction_retry(
        provider, request, first_result, schema, retry_bound, accumulator
    )
    if structured_output is None:
        return await finish_invalid_output(accounting, accumulator.results[-1].content)

    if domain_port is None:
        return await finish_advisory(accounting, structured_output)
    return await finish_domain_write(accounting, structured_output, domain_port)


async def _call_with_timeout_retry(
    provider: LlmProvider,
    request: ProviderRequest,
    retry_bound: int,
    accumulator: CallAccumulator,
) -> ProviderResult | None:
    """AC2: one bounded retry on `ProviderTimeout`. Returns `None` only when
    every attempt timed out."""
    for _ in range(retry_bound + 1):
        try:
            result = await provider.complete(request)
        except ProviderTimeout:
            continue
        accumulator.add(result)
        return result
    return None


async def _validate_with_correction_retry(
    provider: LlmProvider,
    request: ProviderRequest,
    first_result: ProviderResult,
    schema: type[SchemaT],
    retry_bound: int,
    accumulator: CallAccumulator,
) -> SchemaT | None:
    """AC1: validate `first_result`; on failure, retry with an explicit
    correction prompt (code-gen skill's LLM Integration #3) up to
    `retry_bound` times. Returns `None` once every attempt is exhausted, or
    a correction call itself times out."""
    latest = first_result
    for attempt in range(retry_bound + 1):
        try:
            return validate_structured_output(latest.content, schema)
        except StructuredOutputError:
            if attempt == retry_bound:
                return None
            corrected_request = _with_correction(request, schema)
            try:
                latest = await provider.complete(corrected_request)
            except ProviderTimeout:
                return None
            accumulator.add(latest)
    return None


def _with_correction(request: ProviderRequest, schema: type[SchemaT]) -> ProviderRequest:
    correction = {
        "role": "user",
        "content": (
            "Your response did not match the required schema. "
            f"Required: {schema.model_json_schema()}. Please respond again."
        ),
    }
    return request.model_copy(update={"messages": [*request.messages, correction]})
