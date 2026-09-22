"""Snapshot freshness + consistency orchestration (E2-S5 AC5).

The one DB-touching piece of E2-S5: `rules_engine.freshness` and
`rules_engine.consistency` are pure and never see a session or a repository
(layer 4a). This module fetches the current `DelinquencyRecord` through
`DelinquencyRecordRepository` (the sole external boundary, per the code-gen
skill: "only mock external boundaries"), maps the ORM row to the domain
model, and re-checks both freshness and consistency before ever returning a
success value.

This is also the plain, serializable API surface a future
`POST /api/customers/{account_id}/refresh` endpoint calls directly -- no
framework types appear in `refresh_and_check`'s signature or return type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.config.policy.provider import PolicyProvider
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.rules_engine.consistency import RecordCheck, check_consistency
from collectai.rules_engine.freshness import FreshnessCheckResult, check_freshness
from collectai.types.clock import Clock
from collectai.types.enums import Bucket, CollectionStatus, Freshness
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable, RuleFailure, RuleResult


@dataclass(frozen=True, slots=True)
class SnapshotCheckResult:
    """Combined freshness + consistency outcome for one refresh check."""

    freshness: FreshnessCheckResult
    consistency: RecordCheck
    current_record: DelinquencyRecord


async def refresh_and_check(
    session: AsyncSession,
    *,
    account_id: str,
    customer_id: str,
    snapshot_as_of: datetime | None,
    snapshot_version: int,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> RuleResult[SnapshotCheckResult]:
    """Fetch the current record and re-check freshness + consistency (AC5).

    Never returns an eligibility/option/score-shaped success value when the
    record is stale, ambiguous or inconsistent -- only a `RuleResult` whose
    success value proves both checks passed.
    """
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable as exc:
        return RuleResult.fail(RuleFailure(reason_code=exc.reason_code, message=str(exc)))

    orm_record = await DelinquencyRecordRepository().get_by_account(
        session, account_id, customer_id
    )
    if orm_record is None:
        return RuleResult.fail(
            RuleFailure(
                reason_code=ReasonCode.AMBIGUOUS_VALIDATION,
                message=f"No delinquency record found for account {account_id!r}.",
            )
        )
    current_record = _to_domain_record(orm_record)

    freshness_result = check_freshness(
        snapshot_as_of=snapshot_as_of,
        snapshot_version=snapshot_version,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )
    if freshness_result.status is not Freshness.FRESH:
        return _freshness_failure(freshness_result)

    consistency_result = check_consistency(current_record)
    if not consistency_result.consistent:
        return _consistency_failure(consistency_result)

    return RuleResult.success(
        SnapshotCheckResult(
            freshness=freshness_result,
            consistency=consistency_result,
            current_record=current_record,
        )
    )


def _freshness_failure(freshness_result: FreshnessCheckResult) -> RuleResult[SnapshotCheckResult]:
    reason_code = freshness_result.reason_code or ReasonCode.AMBIGUOUS_VALIDATION
    return RuleResult.fail(
        RuleFailure(
            reason_code=reason_code,
            message=f"Snapshot freshness check failed: {freshness_result.status.value}.",
            details={
                "current_record_version": freshness_result.current_record.record_version
            },
        )
    )


def _consistency_failure(consistency_result: RecordCheck) -> RuleResult[SnapshotCheckResult]:
    return RuleResult.fail(
        RuleFailure(
            reason_code=consistency_result.reason_code or ReasonCode.INCONSISTENT_RECORD,
            message="Delinquency record failed internal consistency checks.",
            details={"violations": list(consistency_result.violations)},
        )
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
