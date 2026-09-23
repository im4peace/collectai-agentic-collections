"""Promise-to-Pay domain service (E6-S6; extended by E6-S2 for the
chat-driven path).

Owns the officer-manual PTP workflow's state transitions: dry-run
amount/date validation, the full creation orchestration (freshness,
deterministic validation, conflict/dispute checks, the row insert and its
audit event) and a plain by-id read. This module -- and everything it
imports -- has no dependency on `collectai.ai_orchestration` (AC3): it only
ever talks to `rules_engine`, `persistence`, `audit`, `config.policy` and
`types`, so the manual workflow keeps working with the LLM provider fully
down (`tests/architecture/test_manual_ptp_no_ai.py` asserts this by AST
import scan).

Layering (folder-structure.md section 5): `domain_services` (layer 5a) may
import layers 0-4 but never `api` (layer 7), so every failure mode here is
one of the small, framework-free exceptions in `_ptp_exceptions.py` --
never one of `api.middleware.errors`'s HTTP-shaped exceptions.
`api/routers/ptps.py` catches each of these and translates it to the
matching HTTP error; this keeps the "which HTTP status" decision entirely
in the API layer.

Module split (code-gen skill's 300-line hard block, principle #5): this
file kept growing past 300 lines once idempotency, lookups and row/audit
construction were all written out, so those pieces now live in two
underscore-prefixed sibling modules this file is the sole importer of --
`_ptp_helpers.py` (lookups, dataclasses, wire-dict/row/draft construction)
and `_ptp_idempotency.py` (the `Idempotency-Key` storage the story brief
asks to keep out of any new shared repository/ORM file; see that module's
own docstring for why it is a *separate* file from this one rather than
literally inline). Every name a caller needs is re-exported here, so
`api/routers/ptps.py` only ever imports from `ptp_service` itself.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.service import AuditService
from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._ptp_exceptions import (
    PtpAccountNotFoundError,
    PtpBusinessRuleViolation,
    PtpConflictError,
)
from collectai.domain_services._ptp_helpers import (
    DryRunValidationResult,
    PtpRecordRequest,
    RecordPtpOutcome,
    alternatives_to_dict,
    build_audit_draft,
    build_ptp_row,
    business_violation_message,
    get_delinquency_record,
    has_active_pending_ptp,
    has_open_dispute,
    ptp_wire_dict,
    to_domain_record,
)
from collectai.domain_services._ptp_idempotency import (
    hash_request,
    insert_or_replay,
    replay_if_present,
)
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.freshness import check_freshness
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import Clock
from collectai.types.enums import Freshness, Persona
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

__all__ = [
    "DryRunValidationResult",
    "PtpAccountNotFoundError",
    "PtpBusinessRuleViolation",
    "PtpConflictError",
    "PtpRecordRequest",
    "RecordPtpOutcome",
    "dry_run_validate_ptp",
    "get_ptp_by_id",
    "ptp_wire_dict",
    "record_officer_ptp",
]


async def dry_run_validate_ptp(
    session: AsyncSession,
    *,
    account_id: str,
    promised_amount: str,
    promised_date: date,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> DryRunValidationResult:
    """`POST /api/ptps/validate` (AC1, AC2): amount/date only, no
    conflict/dispute/freshness check -- "the same validator as creation"
    means `validate_ptp` itself, not this endpoint's full write-path
    orchestration. Raises `PtpAccountNotFoundError` for an unknown account,
    or lets `types.results.PolicyUnavailable` propagate fail-closed."""
    policy = policy_provider.get_active()
    record = await get_delinquency_record(session, account_id)
    if record is None:
        raise PtpAccountNotFoundError(account_id)

    outcome = validate_ptp(
        PtpValidationInput(
            promised_amount=promised_amount,
            promised_date=promised_date,
            overdue_amount=record.overdue_amount,
        ),
        policy_provider,
        clock,
    )
    return DryRunValidationResult(
        valid=outcome.valid,
        reason_codes=outcome.reason_codes,
        alternatives=alternatives_to_dict(outcome.alternatives),
        policy_version=policy.policy_version,
    )


async def get_ptp_by_id(session: AsyncSession, ptp_id: str) -> PromiseToPayOrm | None:
    stmt = select(PromiseToPayOrm).where(PromiseToPayOrm.ptp_id == ptp_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def record_officer_ptp(
    session: AsyncSession,
    *,
    request: PtpRecordRequest,
    idempotency_key: str,
    persona: Persona,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> RecordPtpOutcome:
    """`POST /api/ptps` (AC1, AC4, AC5): idempotency replay, freshness,
    deterministic validation, conflict/dispute checks, then the one insert
    plus its audit event in the caller's transaction. The caller (the
    router) commits (see `routers/session.py`'s note on why) and is
    responsible for translating every exception raised here, plus
    `types.results.PolicyUnavailable` and `audit.service.AuditUnavailable`
    (both allowed to propagate unmodified), to the matching HTTP error."""
    request_hash = hash_request(request)
    replay = await replay_if_present(session, idempotency_key, request_hash)
    if replay is not None:
        return replay

    policy = policy_provider.get_active()
    record = await get_delinquency_record(session, request.account_id)
    if record is None:
        raise PtpAccountNotFoundError(request.account_id)
    domain_record = to_domain_record(record)

    _assert_fresh(request, domain_record, policy, clock)
    _assert_amount_and_date_valid(request, record.overdue_amount, policy_provider, clock)
    await _assert_no_conflict(session, request)

    new_row = build_ptp_row(request, record.customer_id, policy.policy_version, clock)
    session.add(new_row)
    await session.flush()
    await audit_service.record_in(session, build_audit_draft(new_row, correlation_id, persona))

    response_body = ptp_wire_dict(new_row)
    replay = await insert_or_replay(
        session,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_body=response_body,
        resource_id=new_row.ptp_id,
        created_at=new_row.created_at,
    )
    if replay is not None:
        return replay
    return RecordPtpOutcome(response_body=response_body, replayed=False)


def _assert_fresh(
    request: PtpRecordRequest, domain_record: DelinquencyRecord, policy: PolicyRuleSet, clock: Clock
) -> None:
    freshness_result = check_freshness(
        snapshot_as_of=request.snapshot_as_of,
        snapshot_version=request.record_version,
        current_record=domain_record,
        policy=policy,
        clock=clock,
    )
    if freshness_result.status is not Freshness.FRESH:
        raise PtpConflictError(
            reason_code=freshness_result.reason_code or ReasonCode.AMBIGUOUS_VALIDATION,
            message=f"Snapshot freshness check failed: {freshness_result.status.value}.",
            context={"refreshed_context": {"record_version": domain_record.record_version}},
        )


def _assert_amount_and_date_valid(
    request: PtpRecordRequest, overdue_amount: Money, policy_provider: PolicyProvider, clock: Clock
) -> None:
    outcome = validate_ptp(
        PtpValidationInput(
            promised_amount=request.promised_amount,
            promised_date=request.promised_date,
            overdue_amount=overdue_amount,
        ),
        policy_provider,
        clock,
    )
    if not outcome.valid:
        reason_code = outcome.reason_codes[0]
        raise PtpBusinessRuleViolation(
            reason_code=reason_code,
            message=business_violation_message(reason_code),
            alternatives=alternatives_to_dict(outcome.alternatives),
        )


async def _assert_no_conflict(session: AsyncSession, request: PtpRecordRequest) -> None:
    if await has_active_pending_ptp(session, request.account_id):
        raise PtpConflictError(
            reason_code=ReasonCode.CONFLICTING_ACTIVE_ITEM,
            message="This account already has an active PENDING promise to pay.",
            context={"permitted_paths": ["cancel", "amend"]},
        )
    if await has_open_dispute(session, account_id=request.account_id, item_id=request.item_id):
        raise PtpConflictError(
            reason_code=ReasonCode.DISPUTED_ITEM,
            message="This item is under an open dispute.",
        )
