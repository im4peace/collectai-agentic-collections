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
construction were all written out, so those pieces now live in
underscore-prefixed sibling modules this file is the sole importer of --
`_ptp_helpers.py` (lookups, dataclasses, wire-dict/row/draft construction),
`_ptp_idempotency.py` (the `Idempotency-Key` storage the story brief asks to
keep out of any new shared repository/ORM file), `_ptp_validation.py` (the
freshness/amount-date/conflict assertions both `record_officer_ptp` and
E6-S2's `_ptp_chat_confirmation.record_chat_ptp` need) and
`_ptp_chat_confirmation.py` (that chat-driven creation path itself). Every
name a caller needs is re-exported here, so `api/routers/ptps.py` and
`application.confirmation_flow` only ever import from `ptp_service` itself.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._ptp_chat_confirmation import record_chat_ptp
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
    get_delinquency_record,
    ptp_wire_dict,
    to_domain_record,
)
from collectai.domain_services._ptp_idempotency import (
    hash_request,
    insert_or_replay,
    replay_if_present,
)
from collectai.domain_services._ptp_validation import (
    assert_amount_and_date_valid,
    assert_fresh,
    assert_no_conflict,
)
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import Clock
from collectai.types.enums import Persona

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
    "record_chat_ptp",
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

    assert_fresh(request, domain_record, policy, clock)
    assert_amount_and_date_valid(request, record.overdue_amount, policy_provider, clock)
    await assert_no_conflict(session, request)

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


