"""Read queries for stored audit events (E1-S4; extended by E9-S1's
`search` and `list_chains` for the audit trail API's filter/pagination and
chain-summary needs). `search` and `list_chains` are pure "fetch what you're
asked for" helpers -- the API router owns interpreting query parameters
(including the `FILTER_REQUIRED` rule) and never this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.types.enums import AuditStage
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


@dataclass(frozen=True, slots=True)
class ChainSummaryRow:
    """One `GET /api/audit/chains` row -- exactly the fields
    `AuditChainSummary` (api-contracts.md section 4) needs, so
    `api/routers/audit.py` can map this straight across without guessing at
    field names."""

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


async def search(
    session: AsyncSession,
    *,
    correlation_id: str | None = None,
    account_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    stages: list[AuditStage] | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditEvent], int]:
    """The requested page of matching events, ordered by
    `(timestamp, sequence)` ascending (the decision-chain order), plus the
    total matching row count (`PageInfo.total`) computed over the same
    filters, ignoring `limit`/`offset`."""
    filters = _build_filters(
        correlation_id=correlation_id,
        account_id=account_id,
        from_ts=from_ts,
        to_ts=to_ts,
        stages=stages,
        event_type=event_type,
    )
    total = await _count_matching(session, filters)
    stmt = (
        select(AuditEventOrm)
        .where(*filters)
        .order_by(AuditEventOrm.timestamp, AuditEventOrm.sequence)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    events = [_to_domain(orm) for orm in result.scalars().all()]
    return events, total


async def list_chains(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ChainSummaryRow], int]:
    """One summary row per distinct `correlation_id` with at least one event
    matching the given filters, newest chain (by last matching event) first,
    plus the total distinct-chain count.

    Each summary describes the chain's *entire* event history (mirroring
    `GET /api/audit?correlation_id=` returning "the whole chain"), not just
    the events that happened to match `from`/`to`/`account_id` -- only which
    correlation ids appear, and their ordering, are filter-dependent. Chains
    are resolved in two passes: a `GROUP BY` picks the page of correlation
    ids (this table is demo-scale, so an extra round trip per chain to reuse
    `list_by_correlation_id`'s existing ordering is preferred here over a
    window-function query that would need re-deriving that ordering)."""
    filters = _build_filters(
        correlation_id=None,
        account_id=account_id,
        from_ts=from_ts,
        to_ts=to_ts,
        stages=None,
        event_type=None,
    )
    total = await _count_distinct_correlation_ids(session, filters)
    chain_ids = await _page_of_chain_ids_newest_first(session, filters, limit=limit, offset=offset)
    summaries = [await _summarize_chain(session, correlation_id) for correlation_id in chain_ids]
    return summaries, total


def _build_filters(
    *,
    correlation_id: str | None,
    account_id: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    stages: list[AuditStage] | None,
    event_type: str | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if correlation_id is not None:
        filters.append(AuditEventOrm.correlation_id == correlation_id)
    if account_id is not None:
        filters.append(AuditEventOrm.account_id == account_id)
    if from_ts is not None:
        filters.append(AuditEventOrm.timestamp >= from_ts)
    if to_ts is not None:
        filters.append(AuditEventOrm.timestamp < to_ts)
    if stages:
        filters.append(AuditEventOrm.stage.in_([stage.value for stage in stages]))
    if event_type is not None:
        filters.append(AuditEventOrm.event_type == event_type)
    return filters


async def _count_matching(session: AsyncSession, filters: list[ColumnElement[bool]]) -> int:
    stmt = select(func.count()).select_from(AuditEventOrm).where(*filters)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _count_distinct_correlation_ids(
    session: AsyncSession, filters: list[ColumnElement[bool]]
) -> int:
    stmt = select(func.count(func.distinct(AuditEventOrm.correlation_id))).where(*filters)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _page_of_chain_ids_newest_first(
    session: AsyncSession,
    filters: list[ColumnElement[bool]],
    *,
    limit: int,
    offset: int,
) -> list[str]:
    stmt = (
        select(AuditEventOrm.correlation_id)
        .where(*filters)
        .group_by(AuditEventOrm.correlation_id)
        .order_by(func.max(AuditEventOrm.timestamp).desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def _summarize_chain(session: AsyncSession, correlation_id: str) -> ChainSummaryRow:
    events = await list_by_correlation_id(session, correlation_id)
    stages_seen = {event.stage for event in events}
    return ChainSummaryRow(
        correlation_id=correlation_id,
        account_id=_first_non_null(event.account_id for event in events),
        started_at=events[0].timestamp,
        last_event_at=events[-1].timestamp,
        event_count=len(events),
        stages_present=[stage for stage in AuditStage if stage in stages_seen],
        final_action=events[-1].final_action,
        policy_version=events[-1].policy_version,
        model_id=events[-1].model_id,
        prompt_version=events[-1].prompt_version,
    )


def _first_non_null(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value is not None:
            return value
    return None
