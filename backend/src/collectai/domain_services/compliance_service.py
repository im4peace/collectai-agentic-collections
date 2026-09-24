"""Compliance review-queue decision capability (E7-S5).

`record_compliance_review_decision` is COMPLIANCE_RISK's one mutating
capability (AC2): it writes exactly one `review_decision` row
(`kind=COMPLIANCE_DECISION`) and transitions the case to DECIDED -- no
balance, `PaymentEvent`, PTP, arrangement, hardship or dispute write is even
reachable from this module (AC4: nothing here imports `arrangement_service`,
`ptp_service`, `payment_service` or `hardship_service`, so there is no code
path by which it could touch those tables). Mirrors `review_service.decide`'s
"idempotency-check, then validate, then authorize, then write" shape, but
narrower: no state-machine branching by action (a compliance decision is
always terminal -- DECIDED), no policy-authority gate (a compliance outcome
is the reviewer's own judgement, not a deterministic eligibility check)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._review_exceptions import (
    ReviewCaseNotFoundError,
    ReviewConflictError,
    ReviewNotPermittedError,
    ReviewValidationError,
)
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.review_decision import ReviewDecisionOrm
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.persistence.repositories.review_decision_repository import ReviewDecisionRepository
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    CaseStatus,
    ComplianceOutcome,
    DecisionKind,
    Persona,
    ReviewQueue,
)
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.reason_codes import ReasonCode

_IDEMPOTENCY_SCOPE = "compliance_decision"
_COMPLIANCE_DECISION_RECORDED_EVENT_TYPE = "COMPLIANCE_DECISION_RECORDED"

_idempotency_repository = IdempotencyRepository()
_review_decision_repository = ReviewDecisionRepository()

_ACTIONABLE_STATUSES: frozenset[str] = frozenset(
    {CaseStatus.OPEN.value, CaseStatus.IN_REVIEW.value, CaseStatus.AWAITING_INFORMATION.value}
)


@dataclass(frozen=True, slots=True)
class ComplianceDecisionRequest:
    case_id: str
    outcome: ComplianceOutcome
    reason: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class ComplianceDecisionOutcome:
    response_body: dict[str, Any]
    replayed: bool


async def record_compliance_review_decision(
    session: AsyncSession,
    *,
    request: ComplianceDecisionRequest,
    reviewer_persona: Persona,
    idempotency_key: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> ComplianceDecisionOutcome:
    request_hash = _hash_request(request)
    existing = await _idempotency_repository.get_by_scope_and_key(
        session, _IDEMPOTENCY_SCOPE, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ReviewConflictError(
                reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
                message="This idempotency key was already used for a different decision.",
            )
        return ComplianceDecisionOutcome(response_body=existing.response_body, replayed=True)

    if not request.reason:
        raise ReviewValidationError(
            reason_code=ReasonCode.REASON_REQUIRED,
            message="A compliance decision requires a reason.",
        )

    case = await session.get(EscalationCaseOrm, request.case_id)
    if case is None:
        raise ReviewCaseNotFoundError(request.case_id)

    _assert_reviewer_persona(reviewer_persona)

    if case.queue != ReviewQueue.COMPLIANCE_REVIEW.value:
        raise ReviewConflictError(
            reason_code=ReasonCode.WRONG_QUEUE,
            message="This case is not in the compliance review queue.",
        )
    if case.status not in _ACTIONABLE_STATUSES:
        raise ReviewConflictError(
            reason_code=ReasonCode.INVALID_STATE_TRANSITION,
            message="This case has already been decided or re-routed.",
        )
    if case.version != request.expected_version:
        raise ReviewConflictError(
            reason_code=ReasonCode.VERSION_CONFLICT,
            message="This case has changed since it was loaded; refresh and retry.",
        )

    policy = policy_provider.get_active()
    now = clock.now()
    decision = ReviewDecisionOrm(
        decision_id=generate_id(EntityPrefix.DECISION),
        case_id=case.case_id,
        kind=DecisionKind.COMPLIANCE_DECISION.value,
        action=None,
        compliance_outcome=request.outcome.value,
        reason=request.reason,
        note=None,
        modification_option_id=None,
        escalate_reason=None,
        rerouted_case_id=None,
        release_suppression=False,
        overrode_ai=False,
        reviewer_persona=reviewer_persona.value,
        decided_at=now,
        case_version_after=case.version + 1,
        policy_version=policy.policy_version,
    )
    await _review_decision_repository.create(session, decision)

    case.status = CaseStatus.DECIDED.value
    case.version += 1
    case.updated_at = now
    case.decided_at = now
    if case.first_reviewed_at is None:
        case.first_reviewed_at = now
    await session.flush()

    await audit_service.record_in(
        session, _build_audit_draft(case, decision, correlation_id, reviewer_persona)
    )

    response_body = _decision_wire_dict(case, decision)

    async def _already_computed() -> dict[str, object]:
        return response_body

    stored_body, _ = await IdempotencyService(clock).get_or_create(
        session,
        scope=_IDEMPOTENCY_SCOPE,
        key=idempotency_key,
        request_hash=request_hash,
        resource_type="review_decision",
        resource_id=decision.decision_id,
        compute_response=_already_computed,
    )
    return ComplianceDecisionOutcome(response_body=stored_body, replayed=False)


def _assert_reviewer_persona(reviewer_persona: Persona) -> None:
    """AC6 (persona-level; the router's `require_capability("compliance:
    decide")` already restricts this to COMPLIANCE_RISK -- defense in
    depth). AC3's object-level half (only a case actually routed to
    COMPLIANCE_REVIEW is actionable) is the queue check just below this
    call, not a separate `reviewer_role` check: `rules_engine.routing
    .route_escalation` always pairs `queue=COMPLIANCE_REVIEW` with
    `reviewer_role=COMPLIANCE_RISK` 1:1, and api-contracts.md's own error
    table reserves `WRONG_QUEUE` (409) for a case outside COMPLIANCE_REVIEW,
    not `WRONG_REVIEWER_ROLE` (403, persona-level only here)."""
    if reviewer_persona is not Persona.COMPLIANCE_RISK:
        raise ReviewNotPermittedError(
            reason_code=ReasonCode.WRONG_REVIEWER_ROLE,
            message="Only compliance/risk may record a compliance review decision.",
        )


def _hash_request(request: ComplianceDecisionRequest) -> str:
    canonical = json.dumps(
        {
            "case_id": request.case_id,
            "outcome": request.outcome.value,
            "reason": request.reason,
            "expected_version": request.expected_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_audit_draft(
    case: EscalationCaseOrm,
    decision: ReviewDecisionOrm,
    correlation_id: str,
    reviewer_persona: Persona,
) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=_COMPLIANCE_DECISION_RECORDED_EVENT_TYPE,
        actor_kind=ActorKind.STAFF,
        actor_persona=reviewer_persona,
        customer_id=case.customer_id,
        account_id=case.account_id,
        capability="compliance:decide",
        policy_version=decision.policy_version,
        reason_code=decision.compliance_outcome,
        final_action=decision.compliance_outcome,
        resource_type="review_decision",
        resource_id=decision.decision_id,
    )


def _decision_wire_dict(case: EscalationCaseOrm, decision: ReviewDecisionOrm) -> dict[str, Any]:
    return {
        "decision_id": decision.decision_id,
        "case_id": decision.case_id,
        "compliance_outcome": decision.compliance_outcome,
        "reason": decision.reason,
        "reviewer_persona": decision.reviewer_persona,
        "decided_at": _iso_z(decision.decided_at),
        "policy_version": decision.policy_version,
        "case_status": case.status,
        "case_version": case.version,
    }


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
