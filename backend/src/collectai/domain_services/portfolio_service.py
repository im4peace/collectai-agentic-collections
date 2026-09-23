"""Delinquent portfolio listing orchestration (E3-S2 AC1-AC4).

`priority_band`/`priority_score` are computed values (data-models.md:
"CollectionsPriority ... [is a] computed value, not a table"), never a SQL
column, so this module is the seam between the SQL-filterable slice of the
query (`DelinquencyRecordRepository.list_portfolio_candidates`: `dpd` range,
`collection_status`, `overdue_amount > 0`) and the two things only
`rules_engine` can produce: the deterministic priority score/band
(`rules_engine.priority.compute_priority`, the single source of truth --
this module never re-derives scoring math) and the internal-consistency
check (`rules_engine.consistency.check_consistency`) that decides whether a
candidate is even eligible to be scored.

Fail-closed (AC4/api-contracts.md 3.3): a `POLICY_UNAVAILABLE` outcome from
`compute_priority` on *any* candidate aborts the whole listing -- callers
must never receive a partially-scored page.

NOTE -- file size: the five per-table ancillary queries that feed
`PriorityInput`'s extra fields (broken PTP count, most recent contact
outcome, open dispute/hardship/escalation) live in
`domain_services/portfolio_priority_extras.py`, split out once this module
crossed the 300-line block threshold (code-gen skill principle #1). This
module keeps the orchestration, the pure filter/sort/paginate helpers and
the ORM<->domain mapping.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.portfolio_priority_extras import gather_priority_extras
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.rules_engine.consistency import check_consistency
from collectai.rules_engine.priority import PriorityInput, PriorityResult, compute_priority
from collectai.types.enums import (
    AccountType,
    ActorKind,
    AuditStage,
    Bucket,
    CollectionStatus,
    PriorityBand,
)
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.results import PolicyUnavailable, RuleFailure, RuleResult

logger = logging.getLogger(__name__)

_EXCLUDED_RECORDS_AUDIT_EVENT_TYPE = "PORTFOLIO_INCONSISTENT_RECORDS_EXCLUDED"
SortBy = Literal["overdue_amount", "dpd", "priority_score"]
SortDir = Literal["asc", "desc"]

_delinquency_repository = DelinquencyRecordRepository()


@dataclass(frozen=True, slots=True)
class PortfolioRow:
    """One fully-scored, consistency-checked candidate (pure data -- no ORM
    or FastAPI types), so `sort_portfolio_rows`/`filter_by_priority_band`/
    `paginate_portfolio_rows` are testable without a database."""

    account_id: str
    customer_id: str
    customer_name: str
    account_type: AccountType
    outstanding_balance: Money
    overdue_amount: Money
    dpd: int
    bucket: Bucket
    collection_status: CollectionStatus
    priority_band: PriorityBand
    priority_score: Decimal
    human_treatment: bool
    automated_treatment_suppressed: bool
    record_version: int


@dataclass(frozen=True, slots=True)
class PortfolioPageResult:
    """The final, paginated portfolio page plus its pre-pagination total."""

    items: list[PortfolioRow]
    total: int
    policy_version: str


async def list_portfolio(
    session: AsyncSession,
    *,
    policy_provider: PolicyProvider,
    audit_service: AuditService,
    correlation_id: str,
    dpd_min: int | None,
    dpd_max: int | None,
    statuses: Sequence[CollectionStatus] | None,
    priority_bands: Sequence[PriorityBand] | None,
    sort_by: SortBy,
    sort_dir: SortDir,
    limit: int,
    offset: int,
) -> RuleResult[PortfolioPageResult]:
    """List, score, filter, sort and paginate the delinquent portfolio."""
    try:
        active_policy_version = policy_provider.get_active().policy_version
    except PolicyUnavailable as exc:
        return RuleResult.fail(RuleFailure(reason_code=exc.reason_code, message=str(exc)))

    candidates = await _delinquency_repository.list_portfolio_candidates(
        session,
        dpd_min=dpd_min,
        dpd_max=dpd_max,
        statuses=[status.value for status in statuses] if statuses else None,
    )

    scored = await _score_consistent_candidates(session, candidates, policy_provider)
    if not scored.ok:
        assert scored.failure is not None  # noqa: S101 - narrows for mypy after `.ok` check
        return RuleResult.fail(scored.failure)
    assert scored.value is not None  # noqa: S101 - narrows for mypy after `.ok` check
    rows, excluded_count = scored.value

    if excluded_count > 0:
        await _record_excluded_count(audit_service, correlation_id, excluded_count)

    filtered = filter_by_priority_band(rows, priority_bands)
    total = len(filtered)
    sorted_rows = sort_portfolio_rows(filtered, sort_by=sort_by, sort_dir=sort_dir)
    page_rows = paginate_portfolio_rows(sorted_rows, limit=limit, offset=offset)

    return RuleResult.success(
        PortfolioPageResult(items=page_rows, total=total, policy_version=active_policy_version)
    )


async def _score_consistent_candidates(
    session: AsyncSession,
    candidates: Sequence[Row[Any]],
    policy_provider: PolicyProvider,
) -> RuleResult[tuple[list[PortfolioRow], int]]:
    """Exclude (never score) any candidate whose `DelinquencyRecord` fails
    `check_consistency` (design guidance (d)); score the rest, aborting the
    whole listing on the first `POLICY_UNAVAILABLE` (design guidance (c))."""
    rows: list[PortfolioRow] = []
    excluded_count = 0
    for delinquency, account, customer in candidates:
        record = _to_domain_record(delinquency)
        if not check_consistency(record).consistent:
            excluded_count += 1
            continue

        priority_result = await _score_one_candidate(session, record, policy_provider)
        if not priority_result.ok:
            assert priority_result.failure is not None  # noqa: S101
            return RuleResult.fail(priority_result.failure)
        assert priority_result.value is not None  # noqa: S101
        rows.append(_to_portfolio_row(account, customer, record, priority_result.value))

    return RuleResult.success((rows, excluded_count))


async def _score_one_candidate(
    session: AsyncSession, record: DelinquencyRecord, policy_provider: PolicyProvider
) -> RuleResult[PriorityResult]:
    extras = await gather_priority_extras(session, record.account_id)
    priority_input = PriorityInput(
        dpd=record.dpd,
        overdue_amount=record.overdue_amount,
        broken_ptp_count=extras.broken_ptp_count,
        recent_contact_outcome=extras.recent_contact_outcome,
        has_active_dispute=extras.has_active_dispute,
        has_active_hardship=extras.has_active_hardship,
        has_open_escalation=extras.has_open_escalation,
    )
    return compute_priority(priority_input, policy_provider)


def filter_by_priority_band(
    rows: list[PortfolioRow], bands: Sequence[PriorityBand] | None
) -> list[PortfolioRow]:
    """`priority_band` filter (OR within the parameter), applied in Python
    since it has no SQL column (design guidance (e))."""
    if not bands:
        return rows
    allowed = set(bands)
    return [row for row in rows if row.priority_band in allowed]


def sort_portfolio_rows(
    rows: list[PortfolioRow], *, sort_by: SortBy, sort_dir: SortDir
) -> list[PortfolioRow]:
    """Exact `Decimal` comparison, never float (api-contracts.md 3.3). Ties
    break by `account_id` ascending regardless of `sort_dir`: a stable
    pre-sort by `account_id` ascending, then a stable sort by the requested
    key, preserves that tie order in either direction."""
    by_account_id_asc = sorted(rows, key=lambda row: row.account_id)
    return sorted(
        by_account_id_asc, key=lambda row: _sort_value(row, sort_by), reverse=(sort_dir == "desc")
    )


def _sort_value(row: PortfolioRow, sort_by: SortBy) -> Decimal:
    if sort_by == "overdue_amount":
        return row.overdue_amount.amount
    if sort_by == "dpd":
        return Decimal(row.dpd)
    return row.priority_score


def paginate_portfolio_rows(
    rows: list[PortfolioRow], *, limit: int, offset: int
) -> list[PortfolioRow]:
    """Slice after filtering and sorting; callers keep `len(rows)` from
    before this call for `PageInfo.total` (design guidance (g))."""
    return rows[offset : offset + limit]


async def _record_excluded_count(
    audit_service: AuditService, correlation_id: str, excluded_count: int
) -> None:
    """Best-effort (design guidance (d)): a failed audit write never fails
    the read -- the portfolio list itself is still returned."""
    draft = AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=_EXCLUDED_RECORDS_AUDIT_EVENT_TYPE,
        actor_kind=ActorKind.SYSTEM,
        rule_results={"excluded_count": excluded_count},
    )
    try:
        await audit_service.record(draft)
    except AuditUnavailable:
        logger.warning(
            "Failed to record PORTFOLIO_INCONSISTENT_RECORDS_EXCLUDED audit event",
            extra={"correlation_id": correlation_id, "excluded_count": excluded_count},
        )


def _to_domain_record(orm_record: DelinquencyRecordOrm) -> DelinquencyRecord:
    return DelinquencyRecord(
        account_id=orm_record.account_id,
        customer_id=orm_record.customer_id,
        outstanding_balance=orm_record.outstanding_balance,
        overdue_amount=orm_record.overdue_amount,
        dpd=orm_record.dpd,
        bucket=Bucket(orm_record.bucket),
        collection_status=CollectionStatus(orm_record.collection_status),
        as_of=orm_record.as_of,
        record_version=orm_record.record_version,
        updated_at=orm_record.updated_at,
    )


def _to_portfolio_row(
    account: AccountOrm,
    customer: CustomerOrm,
    record: DelinquencyRecord,
    priority: PriorityResult,
) -> PortfolioRow:
    return PortfolioRow(
        account_id=record.account_id,
        customer_id=record.customer_id,
        customer_name=customer.display_name,
        account_type=AccountType(account.account_type),
        outstanding_balance=record.outstanding_balance,
        overdue_amount=record.overdue_amount,
        dpd=record.dpd,
        bucket=record.bucket,
        collection_status=record.collection_status,
        priority_band=priority.band,
        priority_score=Decimal(priority.score),
        human_treatment=priority.human_treatment,
        automated_treatment_suppressed=priority.automated_treatment_suppressed,
        record_version=record.record_version,
    )
