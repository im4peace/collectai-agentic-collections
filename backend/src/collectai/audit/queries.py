"""Read queries for stored audit events (E1-S4). Minimal by design: only
what this story's tests need to verify a round trip. `E9-S1` (audit trail
API) extends this module with the fuller chain/filter query set.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.types.models.audit_event import AuditEvent


async def get_by_id(session: AsyncSession, audit_event_id: str) -> AuditEvent | None:
    """The full, redacted `AuditEvent` for one id, or `None` if it does not
    exist."""
    orm = await session.get(AuditEventOrm, audit_event_id)
    if orm is None:
        return None
    return _to_domain(orm)


async def list_by_correlation_id(session: AsyncSession, correlation_id: str) -> list[AuditEvent]:
    """Every audit event sharing `correlation_id`, ordered by
    `(timestamp, sequence)` -- the decision-chain order (system-design.md
    5.4)."""
    stmt = (
        select(AuditEventOrm)
        .where(AuditEventOrm.correlation_id == correlation_id)
        .order_by(AuditEventOrm.timestamp, AuditEventOrm.sequence)
    )
    result = await session.execute(stmt)
    return [_to_domain(orm) for orm in result.scalars().all()]


def _to_domain(orm: AuditEventOrm) -> AuditEvent:
    return AuditEvent(
        audit_event_id=orm.audit_event_id,
        sequence=orm.sequence,
        timestamp=orm.timestamp,
        correlation_id=orm.correlation_id,
        stage=orm.stage,  # type: ignore[arg-type]  # DB CHECK constrains this to a valid AuditStage
        event_type=orm.event_type,
        actor_kind=orm.actor_kind,  # type: ignore[arg-type]  # DB CHECK constrains this to a valid ActorKind
        actor_persona=orm.actor_persona,  # type: ignore[arg-type]
        customer_id=orm.customer_id,
        account_id=orm.account_id,
        capability=orm.capability,
        provider=orm.provider,
        provider_mode=orm.provider_mode,  # type: ignore[arg-type]
        model_id=orm.model_id,
        prompt_version=orm.prompt_version,
        policy_version=orm.policy_version,
        input_ref=orm.input_ref,
        ai_output=orm.ai_output,
        tool_calls=orm.tool_calls,
        rule_results=orm.rule_results,
        human_override=orm.human_override,
        final_action=orm.final_action,
        reason_code=orm.reason_code,
        resource_type=orm.resource_type,
        resource_id=orm.resource_id,
        latency=orm.latency,
        token_usage=orm.token_usage,
    )
