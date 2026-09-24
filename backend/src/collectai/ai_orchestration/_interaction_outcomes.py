"""Terminal outcomes of the fail-closed AI write path (E5-S2 AC1-AC5).

Split out of `orchestrator.py` (300-line block threshold, code-gen skill):
each `_finish_*` function here builds the outcome's audit event and returns
the `AiInteractionResult` `orchestrator.run_ai_interaction` hands back to
its caller. `orchestrator.py` decides *which* of these to call; these
functions decide *what happens* once that path is chosen.
"""

from __future__ import annotations

from typing import Any

from collectai.ai_orchestration._interaction_types import (
    Accounting,
    AiInteractionResult,
    SchemaT,
)
from collectai.ai_orchestration.ports import DomainWritePort
from collectai.audit.events import (
    AI_OUTPUT_INVALID_EVENT_TYPE,
    AI_RESPONSE_RECORDED_EVENT_TYPE,
    POLICY_CONFLICT_EVENT_TYPE,
    PROVIDER_UNAVAILABLE_EVENT_TYPE,
    AuditEventDraft,
    build_ai_interaction_draft,
)
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.types.enums import SafeState

_STRUCTURED_OUTPUT_INVALID_REASON = "STRUCTURED_OUTPUT_INVALID"


async def finish_provider_unavailable(accounting: Accounting) -> AiInteractionResult[Any]:
    """AC2: every provider-timeout attempt exhausted -- safe fallback with
    a human-handoff offer, no state change."""
    draft = build_ai_interaction_draft(
        event_type=PROVIDER_UNAVAILABLE_EVENT_TYPE, **accounting.metadata_kwargs()
    )
    await _record_best_effort(accounting.audit_service, draft)
    return AiInteractionResult(
        safe_state=SafeState.AI_UNAVAILABLE,
        structured_output=None,
        domain_outcome=None,
        offer_handoff=True,
        governed=False,
        unavailable_reason="PROVIDER_TIMEOUT",
    )


async def finish_invalid_output(
    accounting: Accounting, raw_content: str | dict[str, object]
) -> AiInteractionResult[Any]:
    """AC1: every schema-validation retry exhausted -- safe response, no
    state change, the invalid output stored on the audit event."""
    ai_output: dict[str, object] = (
        raw_content if isinstance(raw_content, dict) else {"raw": raw_content}
    )
    draft = build_ai_interaction_draft(
        event_type=AI_OUTPUT_INVALID_EVENT_TYPE,
        ai_output=ai_output,
        reason_code=_STRUCTURED_OUTPUT_INVALID_REASON,
        **accounting.metadata_kwargs(),
    )
    await _record_best_effort(accounting.audit_service, draft)
    return AiInteractionResult(
        safe_state=SafeState.AI_UNAVAILABLE,
        structured_output=None,
        domain_outcome=None,
        offer_handoff=True,
        governed=False,
        unavailable_reason="SCHEMA_INVALID",
    )


async def finish_advisory(
    accounting: Accounting, structured_output: SchemaT
) -> AiInteractionResult[SchemaT]:
    """No `domain_port`: a non-state-changing AI response (e.g. a material
    recommendation). AC5: if its audit event cannot be persisted, the
    orchestrator returns a safe unavailable state rather than presenting
    the response as governed."""
    draft = build_ai_interaction_draft(
        event_type=AI_RESPONSE_RECORDED_EVENT_TYPE,
        ai_output=structured_output.model_dump(mode="json"),
        **accounting.metadata_kwargs(),
    )
    governed = await _record_best_effort(accounting.audit_service, draft)
    return AiInteractionResult(
        safe_state=SafeState.NONE if governed else SafeState.AUDIT_UNAVAILABLE,
        structured_output=structured_output,
        domain_outcome=None,
        offer_handoff=False,
        governed=governed,
        model_id=accounting.accumulator.last_model_id,
    )


async def finish_domain_write(
    accounting: Accounting,
    structured_output: SchemaT,
    domain_port: DomainWritePort[SchemaT],
) -> AiInteractionResult[SchemaT]:
    """AC3, AC4: only schema-validated output ever reaches `domain_port`,
    and only `domain_port.apply` -- authorization, policy validation and the
    deterministic domain service -- decides whether it becomes a state
    change. A rejection is audited here (the applied path audits itself,
    atomically with its own state write); AC5's safe-unavailable fallback
    applies here too, for the same reason it applies to the advisory path."""
    outcome = await domain_port.apply(structured_output)
    if outcome.applied:
        return AiInteractionResult(
            safe_state=SafeState.NONE,
            structured_output=structured_output,
            domain_outcome=outcome,
            offer_handoff=False,
            governed=True,
            model_id=accounting.accumulator.last_model_id,
        )
    draft = build_ai_interaction_draft(
        event_type=POLICY_CONFLICT_EVENT_TYPE,
        ai_output=structured_output.model_dump(mode="json"),
        rule_results=outcome.rule_results,
        reason_code=outcome.reason_code,
        resource_type=outcome.resource_type,
        resource_id=outcome.resource_id,
        **accounting.metadata_kwargs(),
    )
    governed = await _record_best_effort(accounting.audit_service, draft)
    return AiInteractionResult(
        safe_state=SafeState.NONE if governed else SafeState.AUDIT_UNAVAILABLE,
        structured_output=structured_output,
        domain_outcome=outcome,
        offer_handoff=False,
        governed=governed,
        model_id=accounting.accumulator.last_model_id,
    )


async def _record_best_effort(audit_service: AuditService, draft: AuditEventDraft) -> bool:
    """Try to persist a non-state-changing interaction's audit event.
    `AuditService.record` already logs the operational failure (AC5); this
    only turns that failure into a caller-visible boolean."""
    try:
        await audit_service.record(draft)
        return True
    except AuditUnavailable:
        return False
