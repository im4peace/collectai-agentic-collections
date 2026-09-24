"""Dispute review and resolution (E8-S4).

`start_review` (OPEN -> UNDER_REVIEW) and `resolve_dispute` (UNDER_REVIEW ->
RESOLVED, with outcome and reason) are the only writes this story adds,
mirroring `review_service.decide`'s "idempotency-check, then validate, then
authorize, then state-machine guard, then write" shape. AC3 needs no
suppression-release bookkeeping here: `_tool_backend_suppression
.build_suppression_input` already derives `open_disputes` live from
`DisputeStatus(dispute.status) is not DisputeStatus.RESOLVED`
(`rules_engine.suppression.evaluate_suppression` from there) -- setting
`status=RESOLVED` (only together with `outcome`/`resolution_reason`/
`resolved_at`, migration 0004's own `CHECK` constraint) is the entire
mechanism, exactly like `escalation_service`'s own suppression note."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.domain_services._dispute_review_exceptions import (
    DisputeConflictError,
    DisputeNotFoundError,
    DisputeNotPermittedError,
    DisputeValidationError,
)
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, DisputeOutcome, DisputeStatus, Persona
from collectai.types.reason_codes import ReasonCode

_START_REVIEW_SCOPE = "dispute_start_review"
_RESOLVE_SCOPE = "dispute_resolve"
_DISPUTE_UNDER_REVIEW_EVENT_TYPE = "DISPUTE_UNDER_REVIEW"
_DISPUTE_RESOLVED_EVENT_TYPE = "DISPUTE_RESOLVED"
_DISPUTE_RESOLVE_CAPABILITY = "dispute:resolve"

_idempotency_repository = IdempotencyRepository()


@dataclass(frozen=True, slots=True)
class DisputeTransitionOutcome:
    response_body: dict[str, Any]
    replayed: bool


async def start_review(
    session: AsyncSession,
    *,
    dispute_id: str,
    expected_version: int,
    reviewer_persona: Persona,
    idempotency_key: str,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> DisputeTransitionOutcome:
    """AC2: OPEN -> UNDER_REVIEW, audited with the reviewer persona."""
    request_hash = _hash_request(_START_REVIEW_SCOPE, dispute_id, expected_version)
    existing = await _idempotency_repository.get_by_scope_and_key(
        session, _START_REVIEW_SCOPE, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise DisputeConflictError(
                reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
                message="This idempotency key was already used for a different request.",
            )
        return DisputeTransitionOutcome(response_body=existing.response_body, replayed=True)

    _assert_reviewer_persona(reviewer_persona)
    dispute = await _load_dispute(session, dispute_id)
    if dispute.version != expected_version:
        raise DisputeConflictError(
            reason_code=ReasonCode.VERSION_CONFLICT,
            message="This dispute has changed since it was loaded; refresh and retry.",
        )
    if DisputeStatus(dispute.status) is not DisputeStatus.OPEN:
        raise DisputeConflictError(
            reason_code=ReasonCode.INVALID_STATE_TRANSITION,
            message="Only an OPEN dispute can move to UNDER_REVIEW.",
        )

    now = clock.now()
    dispute.status = DisputeStatus.UNDER_REVIEW.value
    dispute.version += 1
    dispute.updated_at = now
    await session.flush()

    await audit_service.record_in(
        session,
        _build_audit_draft(
            dispute, _DISPUTE_UNDER_REVIEW_EVENT_TYPE, correlation_id, reviewer_persona
        ),
    )

    response_body = _dispute_transition_wire_dict(dispute)
    stored_body = await _store_idempotent_result(
        session, clock, _START_REVIEW_SCOPE, idempotency_key, request_hash, dispute, response_body
    )
    return DisputeTransitionOutcome(response_body=stored_body, replayed=False)


async def resolve_dispute(
    session: AsyncSession,
    *,
    dispute_id: str,
    outcome: DisputeOutcome | None,
    reason: str | None,
    expected_version: int,
    reviewer_persona: Persona,
    idempotency_key: str,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> DisputeTransitionOutcome:
    """AC1, AC2, AC3: UNDER_REVIEW -> RESOLVED, only with a non-empty
    `reason` and a real `outcome` -- both written in the same row update
    that sets `status=RESOLVED`, so suppression for this dispute's item
    lifts only once, atomically with the outcome being recorded."""
    request_hash = _hash_resolve_request(dispute_id, outcome, reason, expected_version)
    existing = await _idempotency_repository.get_by_scope_and_key(
        session, _RESOLVE_SCOPE, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise DisputeConflictError(
                reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
                message="This idempotency key was already used for a different request.",
            )
        return DisputeTransitionOutcome(response_body=existing.response_body, replayed=True)

    if outcome is None:
        raise DisputeValidationError(
            reason_code=ReasonCode.OUTCOME_REQUIRED,
            message="Resolving a dispute requires an outcome.",
        )
    if not reason:
        raise DisputeValidationError(
            reason_code=ReasonCode.REASON_REQUIRED,
            message="Resolving a dispute requires a reason.",
        )

    _assert_reviewer_persona(reviewer_persona)
    dispute = await _load_dispute(session, dispute_id)
    if dispute.version != expected_version:
        raise DisputeConflictError(
            reason_code=ReasonCode.VERSION_CONFLICT,
            message="This dispute has changed since it was loaded; refresh and retry.",
        )
    if DisputeStatus(dispute.status) is not DisputeStatus.UNDER_REVIEW:
        raise DisputeConflictError(
            reason_code=ReasonCode.INVALID_STATE_TRANSITION,
            message="Only a dispute UNDER_REVIEW can be resolved.",
        )

    now = clock.now()
    dispute.status = DisputeStatus.RESOLVED.value
    dispute.outcome = outcome.value
    dispute.resolution_reason = reason
    dispute.resolved_at = now
    dispute.version += 1
    dispute.updated_at = now
    await session.flush()

    await audit_service.record_in(
        session,
        _build_audit_draft(dispute, _DISPUTE_RESOLVED_EVENT_TYPE, correlation_id, reviewer_persona),
    )

    response_body = _dispute_transition_wire_dict(dispute)
    stored_body = await _store_idempotent_result(
        session, clock, _RESOLVE_SCOPE, idempotency_key, request_hash, dispute, response_body
    )
    return DisputeTransitionOutcome(response_body=stored_body, replayed=False)


def _assert_reviewer_persona(reviewer_persona: Persona) -> None:
    """AC4 (persona-level; the router's `require_capability("dispute:
    resolve")` already restricts this to COLLECTIONS_OFFICER -- defense in
    depth)."""
    if reviewer_persona is not Persona.COLLECTIONS_OFFICER:
        raise DisputeNotPermittedError(
            reason_code=ReasonCode.WRONG_REVIEWER_ROLE,
            message="Only a collections officer may resolve a dispute.",
        )


async def _load_dispute(session: AsyncSession, dispute_id: str) -> DisputeOrm:
    dispute = await session.get(DisputeOrm, dispute_id)
    if dispute is None:
        raise DisputeNotFoundError(dispute_id)
    return dispute


async def _store_idempotent_result(
    session: AsyncSession,
    clock: Clock,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    dispute: DisputeOrm,
    response_body: dict[str, object],
) -> dict[str, object]:
    async def _already_computed() -> dict[str, object]:
        return response_body

    stored_body, _ = await IdempotencyService(clock).get_or_create(
        session,
        scope=scope,
        key=idempotency_key,
        request_hash=request_hash,
        resource_type="dispute",
        resource_id=dispute.dispute_id,
        compute_response=_already_computed,
    )
    return stored_body


def _hash_request(scope: str, dispute_id: str, expected_version: int) -> str:
    canonical = json.dumps(
        {"scope": scope, "dispute_id": dispute_id, "expected_version": expected_version},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_resolve_request(
    dispute_id: str, outcome: DisputeOutcome | None, reason: str | None, expected_version: int
) -> str:
    canonical = json.dumps(
        {
            "dispute_id": dispute_id,
            "outcome": outcome.value if outcome is not None else None,
            "reason": reason,
            "expected_version": expected_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_audit_draft(
    dispute: DisputeOrm, event_type: str, correlation_id: str, reviewer_persona: Persona
) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=event_type,
        actor_kind=ActorKind.STAFF,
        actor_persona=reviewer_persona,
        customer_id=dispute.customer_id,
        account_id=dispute.account_id,
        capability=_DISPUTE_RESOLVE_CAPABILITY,
        reason_code=dispute.outcome,
        final_action=event_type,
        resource_type="dispute",
        resource_id=dispute.dispute_id,
    )


def _dispute_transition_wire_dict(dispute: DisputeOrm) -> dict[str, Any]:
    return {
        "dispute_id": dispute.dispute_id,
        "account_id": dispute.account_id,
        "customer_id": dispute.customer_id,
        "item_id": dispute.item_id,
        "category": dispute.category,
        "customer_reason": dispute.customer_reason,
        "status": dispute.status,
        "outcome": dispute.outcome,
        "resolution_reason": dispute.resolution_reason,
        "conversation_id": dispute.conversation_id,
        "escalation_case_id": dispute.escalation_case_id,
        "created_at": _iso_z(dispute.created_at),
        "resolved_at": _iso_z(dispute.resolved_at) if dispute.resolved_at is not None else None,
        "version": dispute.version,
    }


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
