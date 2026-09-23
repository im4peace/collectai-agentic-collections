"""Response wire models for `GET /api/audit` and `GET /api/audit/chains`
(api-contracts.md 3.12; section 4 schemas `AuditEvent`, `ToolCallRecord`,
`LatencyInfo`, `TokenUsage`, `AuditPage`, `AuditChainSummary`,
`AuditChainPage`, `PageInfo`).

These are read-only shapes built from the already-stored, already-redacted
`collectai.types.models.audit_event.AuditEvent` domain model (E1-S4). This
module performs no redaction of its own -- AC4's guarantee ("no secrets or
prohibited identifiers") is enforced exactly once, at write time, by
`audit.service.AuditService`; the converters here only reshape what is
already safe to read. Field conversion from the audit row's untyped JSONB
blobs (`tool_calls`, `latency`, `token_usage`) is defensive (`.get()` with
safe defaults) because those columns are not schema-enforced at the database
level -- a row's shape is only as strict as the `AuditEventDraft` the
producing story wrote it with.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import ActorKind, AuditStage, Persona, ProviderMode
from collectai.types.models.audit_event import AuditEvent as AuditEventDomain

_STAGE_ORDER: tuple[AuditStage, ...] = tuple(AuditStage)


class PageInfo(BaseModel):
    """Offset pagination block (api-contracts.md `PageInfo`)."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int
    total: int


class ToolCallRecord(BaseModel):
    """One AI tool call (api-contracts.md `ToolCallRecord`)."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    tool_type: str
    arguments: dict[str, Any]
    result_status: str
    idempotency_key: str | None
    duration_ms: int


class LatencyInfo(BaseModel):
    """Timing capture points (api-contracts.md `LatencyInfo`)."""

    model_config = ConfigDict(frozen=True)

    provider_latency_ms: int | None
    tool_call_duration_ms: int | None
    interaction_duration_ms: int | None


class TokenUsage(BaseModel):
    """Token usage where available (api-contracts.md `TokenUsage`)."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str | None


class AuditEventOut(BaseModel):
    """`AuditEvent` response shape (api-contracts.md section 4). Named
    `AuditEventOut` rather than `AuditEvent` to avoid colliding with the
    domain model (`collectai.types.models.audit_event.AuditEvent`) this is
    built from."""

    model_config = ConfigDict(frozen=True)

    audit_event_id: str
    sequence: int
    timestamp: datetime
    correlation_id: str
    stage: AuditStage
    event_type: str
    actor_kind: ActorKind
    actor_persona: Persona | None
    customer_id: str | None
    account_id: str | None
    capability: str | None
    provider: str | None
    provider_mode: ProviderMode | None
    model_id: str | None
    prompt_version: str | None
    policy_version: str | None
    input_ref: str | None
    ai_output: dict[str, Any] | None
    tool_calls: list[ToolCallRecord]
    rule_results: dict[str, Any] | None
    human_override: dict[str, Any] | None
    final_action: str | None
    reason_code: str | None
    resource_type: str | None
    resource_id: str | None
    latency: LatencyInfo | None
    token_usage: TokenUsage | None


class AuditPage(BaseModel):
    """Audit events (api-contracts.md `AuditPage`)."""

    model_config = ConfigDict(frozen=True)

    items: list[AuditEventOut]
    page: PageInfo


class AuditChainSummary(BaseModel):
    """One decision chain (api-contracts.md `AuditChainSummary`)."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str
    account_id: str | None
    started_at: datetime
    last_event_at: datetime
    event_count: int
    stages_present: list[AuditStage]
    final_action: str | None
    policy_version: str | None
    model_id: str | None
    prompt_version: str | None


class AuditChainPage(BaseModel):
    """Chain summaries (api-contracts.md `AuditChainPage`)."""

    model_config = ConfigDict(frozen=True)

    items: list[AuditChainSummary]
    page: PageInfo


def audit_event_to_response(event: AuditEventDomain) -> AuditEventOut:
    """Convert one stored, redacted `AuditEvent` to its API response
    shape."""
    return AuditEventOut(
        audit_event_id=event.audit_event_id,
        sequence=event.sequence,
        timestamp=event.timestamp,
        correlation_id=event.correlation_id,
        stage=event.stage,
        event_type=event.event_type,
        actor_kind=event.actor_kind,
        actor_persona=event.actor_persona,
        customer_id=event.customer_id,
        account_id=event.account_id,
        capability=event.capability,
        provider=event.provider,
        provider_mode=event.provider_mode,
        model_id=event.model_id,
        prompt_version=event.prompt_version,
        policy_version=event.policy_version,
        input_ref=event.input_ref,
        ai_output=event.ai_output,
        tool_calls=[_tool_call_from_dict(raw) for raw in event.tool_calls],
        rule_results=event.rule_results,
        human_override=event.human_override,
        final_action=event.final_action,
        reason_code=event.reason_code,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        latency=_latency_from_dict(event.latency),
        token_usage=_token_usage_from_dict(event.token_usage),
    )


def dedupe_stages_present(stages: set[AuditStage]) -> list[AuditStage]:
    """Distinct stages seen in a chain, in the stable `AuditStage`
    declaration order rather than event-encounter order (a "unique list
    field" per this codebase's field-dedup convention: never emit the same
    stage twice even when a chain records it more than once)."""
    return [stage for stage in _STAGE_ORDER if stage in stages]


def _tool_call_from_dict(raw: dict[str, Any]) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=str(raw.get("tool_name", "")),
        tool_type=str(raw.get("tool_type", "")),
        arguments=dict(raw.get("arguments") or {}),
        result_status=str(raw.get("result_status", "")),
        idempotency_key=_optional_str(raw.get("idempotency_key")),
        duration_ms=int(raw.get("duration_ms") or 0),
    )


def _latency_from_dict(raw: dict[str, Any] | None) -> LatencyInfo | None:
    if raw is None:
        return None
    return LatencyInfo(
        provider_latency_ms=_optional_int(raw.get("provider_latency_ms")),
        tool_call_duration_ms=_optional_int(raw.get("tool_call_duration_ms")),
        interaction_duration_ms=_optional_int(raw.get("interaction_duration_ms")),
    )


def _token_usage_from_dict(raw: dict[str, Any] | None) -> TokenUsage | None:
    if raw is None:
        return None
    return TokenUsage(
        input_tokens=int(raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        estimated_cost_usd=_optional_str(raw.get("estimated_cost_usd")),
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
