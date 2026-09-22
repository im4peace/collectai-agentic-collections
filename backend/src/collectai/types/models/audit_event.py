"""AuditEvent domain model (data-models.md AuditEvent). Immutable, append-only."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from collectai.types.enums import ActorKind, AuditStage, Persona, ProviderMode
from collectai.types.ids import EntityPrefix, id_validator

AuditEventId = Annotated[str, AfterValidator(id_validator(EntityPrefix.AUDIT_EVENT))]
CustomerId = Annotated[str, AfterValidator(id_validator(EntityPrefix.CUSTOMER))]
AccountId = Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]


class AuditEvent(BaseModel):
    """Immutable, append-only audit record (data-models.md AuditEvent)."""

    model_config = ConfigDict(frozen=True)

    audit_event_id: AuditEventId
    sequence: int
    timestamp: datetime
    correlation_id: str = Field(max_length=64)
    stage: AuditStage
    event_type: str = Field(max_length=80)
    actor_kind: ActorKind
    actor_persona: Persona | None
    customer_id: CustomerId | None
    account_id: AccountId | None
    capability: str | None = Field(default=None, max_length=40)
    provider: str | None = Field(default=None, max_length=40)
    provider_mode: ProviderMode | None
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
