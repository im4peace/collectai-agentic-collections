"""Audit event draft: the fields a caller supplies (E1-S4 AC1).

`AuditEventDraft` mirrors `collectai.types.models.audit_event.AuditEvent`
minus `audit_event_id`, `sequence` and `timestamp` -- those three are
assigned by `AuditService` itself, never by the caller: the id is generated
app-side, the timestamp comes from the injected `Clock` (AC1), and the
sequence is a database identity column assigned on insert. This is the
"builder" this module is named for.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from collectai.types.enums import ActorKind, AuditStage, Persona, ProviderMode
from collectai.types.models.audit_event import AccountId, CustomerId

# Event-type constants for `ai_orchestration.orchestrator` (E5-S2), the
# first caller of `build_ai_interaction_draft` below. Grouped here, next to
# the draft they build, rather than scattered as local constants in the
# producing module, since all three describe outcomes of the *same*
# fail-closed write path (BRD 10.3) and a reader auditing that path should
# find them in one place.
AI_OUTPUT_INVALID_EVENT_TYPE = "AI_OUTPUT_INVALID"
PROVIDER_UNAVAILABLE_EVENT_TYPE = "PROVIDER_UNAVAILABLE"
POLICY_CONFLICT_EVENT_TYPE = "POLICY_CONFLICT"
AI_RESPONSE_RECORDED_EVENT_TYPE = "AI_RESPONSE_RECORDED"


class AuditEventDraft(BaseModel):
    """Caller-supplied audit event fields (E1-S4 AC1)."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str = Field(max_length=64)
    stage: AuditStage
    event_type: str = Field(max_length=80)
    actor_kind: ActorKind
    actor_persona: Persona | None = None
    customer_id: CustomerId | None = None
    account_id: AccountId | None = None
    capability: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=40)
    provider_mode: ProviderMode | None = None
    model_id: str | None = Field(default=None, max_length=120)
    prompt_version: str | None = Field(default=None, max_length=40)
    policy_version: str | None = Field(default=None, max_length=40)
    input_ref: str | None = None
    ai_output: dict[str, object] | None = None
    tool_calls: list[dict[str, object]] = Field(default_factory=list)
    rule_results: dict[str, object] | None = None
    human_override: dict[str, object] | None = None
    final_action: str | None = Field(default=None, max_length=120)
    reason_code: str | None = Field(default=None, max_length=60)
    resource_type: str | None = Field(default=None, max_length=40)
    resource_id: str | None = None
    latency: dict[str, object] | None = None
    token_usage: dict[str, object] | None = None


def build_ai_interaction_draft(
    *,
    correlation_id: str,
    event_type: str,
    capability: str,
    provider: str,
    provider_mode: ProviderMode,
    prompt_version: str,
    stage: AuditStage = AuditStage.AI_INTERPRETATION,
    actor_persona: Persona | None = None,
    customer_id: CustomerId | None = None,
    account_id: AccountId | None = None,
    model_id: str | None = None,
    policy_version: str | None = None,
    ai_output: dict[str, object] | None = None,
    rule_results: dict[str, object] | None = None,
    final_action: str | None = None,
    reason_code: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    latency: dict[str, object] | None = None,
    token_usage: dict[str, object] | None = None,
) -> AuditEventDraft:
    """Build the AI-interaction-shaped `AuditEventDraft` every AI call
    records (E5-S2 AC6: provider latency, tool-call duration, end-to-end
    interaction duration, token usage, model id, prompt version,
    PolicyRuleSet version and correlation id). `actor_kind` is always `AI`
    -- a human-attributed audit event (e.g. AC2's `ACCESS_DENIED`) is built
    directly from `AuditEventDraft` instead, since it is not an AI
    interaction."""
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=stage,
        event_type=event_type,
        actor_kind=ActorKind.AI,
        actor_persona=actor_persona,
        customer_id=customer_id,
        account_id=account_id,
        capability=capability,
        provider=provider,
        provider_mode=provider_mode,
        model_id=model_id,
        prompt_version=prompt_version,
        policy_version=policy_version,
        ai_output=ai_output,
        rule_results=rule_results,
        final_action=final_action,
        reason_code=reason_code,
        resource_type=resource_type,
        resource_id=resource_id,
        latency=latency,
        token_usage=token_usage,
    )
