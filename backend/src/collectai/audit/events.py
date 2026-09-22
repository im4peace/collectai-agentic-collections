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
