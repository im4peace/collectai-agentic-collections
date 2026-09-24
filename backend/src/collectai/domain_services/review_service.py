"""Review queue reviewer-action decisions (E7-S2).

`decide` is the one write path this story adds: APPROVE, REJECT, MODIFY,
REQUEST_MORE_INFORMATION and ESCALATE, each producing one `review_decision`
row (insert-only, never updated -- see that ORM module's own docstring) plus
the matching `escalation_case` state transition and audit event, in one
transaction. Mirrors `application.confirmation_flow.confirm_proposal`'s
"idempotency-check, then revalidate, then write" shape:

1. Idempotency-key replay check first (AC7) -- a genuine replay never
   re-validates or re-writes anything, even if the case has moved on since.
2. Structural validation (AC1, AC6): reason/note/escalate_reason presence,
   with no I/O.
3. Object-level authorization (AC5): only `COLLECTIONS_OFFICER`, and only
   for a case whose own `reviewer_role` is `COLLECTIONS_OFFICER` -- a case
   routed to `COMPLIANCE_REVIEW` is never actionable here even by an
   officer, mirroring `api/routers/me_ownership.require_owned`'s
   "object-level, not just persona-level" pattern for a different resource.
4. State-machine guard (AC8) and optimistic version check (AC4) -- the
   version check alone already makes AC7's "a different decision on an
   already-decided case returns 409" true (that case's version has already
   moved past what a stale caller believes), so no separate bookkeeping is
   needed for it.
5. Per-action deterministic checks: APPROVE's policy-permitted-case-type
   gate (AC2, `policy.parameters.exception.authority`), MODIFY's eligible-
   option gate (AC3, `rules_engine.arrangement.get_eligible_options` --
   the same deterministic service E8-S1 offers arrangement options from),
   ESCALATE's whitelisted-reason gate (AC6,
   `policy.parameters.routing.reviewer_escalation_reasons`) with the
   destination decided by `rules_engine.routing.route_escalation`, never by
   the reviewer.
6. The write: one `review_decision` row, the case's status/version bump,
   and (ESCALATE only) a new `escalation_case` via
   `escalation_service.create_escalation(parent_case_id=...)`.
"""

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
from collectai.domain_services._arrangement_exceptions import (
    ArrangementConflictError,
    ArrangementNotEligibleError,
)
from collectai.domain_services._arrangement_helpers import has_active_arrangement
from collectai.domain_services._ptp_helpers import has_active_pending_ptp
from collectai.domain_services._review_exceptions import (
    ReviewCaseNotFoundError,
    ReviewConflictError,
    ReviewNotPermittedError,
    ReviewValidationError,
)
from collectai.domain_services.arrangement_service import (
    arrangement_wire_dict,
    create_exceptional_arrangement_from_review,
)
from collectai.domain_services.escalation_service import create_escalation
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.review_decision import ReviewDecisionOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.persistence.repositories.review_decision_repository import ReviewDecisionRepository
from collectai.rules_engine.arrangement import get_eligible_options
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    CaseSource,
    CaseStatus,
    DecisionKind,
    EligibilityClass,
    EscalationReason,
    Persona,
    ReviewAction,
    ReviewerRole,
)
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.reason_codes import ReasonCode

_IDEMPOTENCY_SCOPE = "review_decision"
_REVIEW_DECISION_RECORDED_EVENT_TYPE = "REVIEW_DECISION_RECORDED"

_idempotency_repository = IdempotencyRepository()
_review_decision_repository = ReviewDecisionRepository()
_delinquency_repository = DelinquencyRecordRepository()

_ACTIONABLE_STATUSES: frozenset[str] = frozenset(
    {CaseStatus.OPEN.value, CaseStatus.IN_REVIEW.value, CaseStatus.AWAITING_INFORMATION.value}
)
_REASON_REQUIRED_ACTIONS: frozenset[ReviewAction] = frozenset(
    {ReviewAction.APPROVE, ReviewAction.REJECT, ReviewAction.MODIFY, ReviewAction.ESCALATE}
)
"""AC1 names REJECT/MODIFY/ESCALATE explicitly; APPROVE is included too
because migration 0005's own `review_decision_check2` CHECK constraint
already requires `reason IS NOT NULL` for all four (`action IN ('REJECT',
'MODIFY','ESCALATE','APPROVE')`) -- this validates it before the write
reaches that constraint, with the specific `REASON_REQUIRED` reason code
instead of an opaque DB error."""


@dataclass(frozen=True, slots=True)
class ReviewDecisionRequest:
    """The reviewer-submitted fields `POST /api/escalations/{case_id}
    /decisions` needs, decoupled from the Pydantic request schema (layering,
    see `ptp_service.py`'s module docstring for why `domain_services` never
    imports `api.schemas`)."""

    case_id: str
    action: ReviewAction
    expected_version: int
    reason: str | None = None
    note: str | None = None
    modification_option_id: str | None = None
    escalate_reason: EscalationReason | None = None


@dataclass(frozen=True, slots=True)
class ReviewDecisionOutcome:
    response_body: dict[str, Any]
    replayed: bool


async def decide(
    session: AsyncSession,
    *,
    request: ReviewDecisionRequest,
    reviewer_persona: Persona,
    idempotency_key: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> ReviewDecisionOutcome:
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
        return ReviewDecisionOutcome(response_body=existing.response_body, replayed=True)

    _validate_shape(request)
    case = await _load_case(session, request.case_id)
    _assert_reviewer_may_act(case, reviewer_persona)
    _assert_case_actionable(case)
    if case.version != request.expected_version:
        raise ReviewConflictError(
            reason_code=ReasonCode.VERSION_CONFLICT,
            message="This case has changed since it was loaded; refresh and retry.",
        )

    policy = policy_provider.get_active()
    record: DelinquencyRecordOrm | None = None
    if request.action is ReviewAction.APPROVE:
        record = await _delinquency_repository.get_by_account(
            session, case.account_id, case.customer_id
        )
        _assert_approval_permitted(case, policy, record)
    if request.action is ReviewAction.MODIFY:
        await _assert_modification_eligible(session, case, request, policy_provider, clock)
    if request.action is ReviewAction.ESCALATE:
        _assert_escalate_reason_whitelisted(request.escalate_reason, policy)

    rerouted_case_id: str | None = None
    if request.action is ReviewAction.ESCALATE:
        assert request.escalate_reason is not None  # noqa: S101 - _validate_shape guarantees this
        creation = await create_escalation(
            session,
            reason=request.escalate_reason,
            customer_id=case.customer_id,
            account_id=case.account_id,
            conversation_id=case.conversation_id,
            item_id=case.item_id,
            source=CaseSource.REVIEWER,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            parent_case_id=case.case_id,
        )
        rerouted_case_id = creation.case.case_id

    # E7-S4 AC5: an APPROVE of an EXCEPTIONAL_ARRANGEMENT case creates the
    # arrangement only here, after every check above already passed, and
    # only through `arrangement_service` (never inline) -- the LLM never
    # created this arrangement (D-041); a human's explicit APPROVE did.
    arrangement_row: PaymentArrangementOrm | None = None
    if (
        request.action is ReviewAction.APPROVE
        and case.reason == EscalationReason.EXCEPTIONAL_ARRANGEMENT.value
    ):
        assert record is not None  # noqa: S101 - _assert_approval_permitted already required it
        installment_count = (case.requested_terms or {}).get("installment_count")
        if not isinstance(installment_count, int):
            raise ReviewValidationError(
                reason_code=ReasonCode.FREE_FORM_AMOUNT_NOT_ALLOWED,
                message="This case has no valid requested installment count to approve.",
            )
        try:
            arrangement_row = await create_exceptional_arrangement_from_review(
                session,
                record=record,
                installment_count=installment_count,
                exception_case_id=case.case_id,
                reviewer_persona=reviewer_persona,
                policy_provider=policy_provider,
                clock=clock,
                audit_service=audit_service,
                correlation_id=correlation_id,
            )
        except ArrangementConflictError as exc:
            raise ReviewConflictError(reason_code=exc.reason_code, message=exc.message) from exc
        except ArrangementNotEligibleError as exc:
            raise ReviewValidationError(
                reason_code=ReasonCode.FREE_FORM_AMOUNT_NOT_ALLOWED, message=exc.message
            ) from exc

    target_status = _target_status_for(request.action)
    now = clock.now()
    decision = ReviewDecisionOrm(
        decision_id=generate_id(EntityPrefix.DECISION),
        case_id=case.case_id,
        kind=DecisionKind.REVIEWER_ACTION.value,
        action=request.action.value,
        compliance_outcome=None,
        reason=request.reason,
        note=request.note,
        modification_option_id=request.modification_option_id,
        escalate_reason=request.escalate_reason.value if request.escalate_reason else None,
        rerouted_case_id=rerouted_case_id,
        release_suppression=False,
        overrode_ai=False,
        reviewer_persona=reviewer_persona.value,
        decided_at=now,
        case_version_after=case.version + 1,
        policy_version=policy.policy_version,
    )
    await _review_decision_repository.create(session, decision)

    case.status = target_status.value
    case.rerouted_to_case_id = rerouted_case_id
    case.version += 1
    case.updated_at = now
    if case.first_reviewed_at is None:
        case.first_reviewed_at = now
    if target_status is CaseStatus.DECIDED:
        case.decided_at = now
    await session.flush()

    await audit_service.record_in(
        session, _build_audit_draft(case, decision, correlation_id, reviewer_persona)
    )

    response_body = _decision_wire_dict(case, decision, arrangement_row)

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
    return ReviewDecisionOutcome(response_body=stored_body, replayed=False)


def _hash_request(request: ReviewDecisionRequest) -> str:
    canonical = json.dumps(
        {
            "case_id": request.case_id,
            "action": request.action.value,
            "expected_version": request.expected_version,
            "reason": request.reason,
            "note": request.note,
            "modification_option_id": request.modification_option_id,
            "escalate_reason": request.escalate_reason.value if request.escalate_reason else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_shape(request: ReviewDecisionRequest) -> None:
    if request.action in _REASON_REQUIRED_ACTIONS and not request.reason:
        raise ReviewValidationError(
            reason_code=ReasonCode.REASON_REQUIRED,
            message=f"{request.action.value} requires a reason.",
        )
    if request.action is ReviewAction.REQUEST_MORE_INFORMATION and not request.note:
        raise ReviewValidationError(
            reason_code=ReasonCode.NOTE_REQUIRED,
            message="REQUEST_MORE_INFORMATION requires a note.",
        )
    if request.action is ReviewAction.ESCALATE and request.escalate_reason is None:
        raise ReviewValidationError(
            reason_code=ReasonCode.ESCALATE_REASON_REQUIRED,
            message="ESCALATE requires an escalate_reason.",
        )


async def _load_case(session: AsyncSession, case_id: str) -> EscalationCaseOrm:
    case = await session.get(EscalationCaseOrm, case_id)
    if case is None:
        raise ReviewCaseNotFoundError(case_id)
    return case


def _assert_reviewer_may_act(case: EscalationCaseOrm, reviewer_persona: Persona) -> None:
    """AC5: persona-level (only `COLLECTIONS_OFFICER` may call `decide` at
    all -- the router's `require_capability("escalation:review")` already
    enforces this too, this is defense in depth) and object-level (this
    specific case's own `reviewer_role`, e.g. a `COMPLIANCE_REVIEW`-queue
    case, is never actionable here regardless of persona)."""
    if reviewer_persona is not Persona.COLLECTIONS_OFFICER:
        raise ReviewNotPermittedError(
            reason_code=ReasonCode.WRONG_REVIEWER_ROLE,
            message="Only a collections officer may record a reviewer decision.",
        )
    if case.reviewer_role != ReviewerRole.COLLECTIONS_OFFICER.value:
        raise ReviewNotPermittedError(
            reason_code=ReasonCode.WRONG_REVIEWER_ROLE,
            message="This case is not assigned to the collections-officer reviewer role.",
        )


def _assert_case_actionable(case: EscalationCaseOrm) -> None:
    if case.status not in _ACTIONABLE_STATUSES:
        raise ReviewConflictError(
            reason_code=ReasonCode.CASE_ALREADY_DECIDED,
            message="This case has already been decided or re-routed.",
        )


def _assert_approval_permitted(
    case: EscalationCaseOrm, policy: Any, record: DelinquencyRecordOrm | None
) -> None:
    """E7-S2 AC2 / E7-S4 AC4: a case with no `exception_types` at all has
    nothing exceptional to approve, so no policy restriction applies. A
    case whose `exception_types` includes anything outside
    `policy.parameters.exception.authority.collections_officer.types`, or
    whose account's current overdue amount exceeds that same authority's
    `max_overdue_amount`, is not policy-permitted for this reviewer role --
    both the exception *type* and the *threshold* (E7-S4 AC4's "exception
    type, thresholds and maximum overdue amount") gate APPROVE, not type
    alone."""
    if not case.exception_types:
        return
    authority = policy.parameters.exception.authority.collections_officer
    authorized_types = {t.value for t in authority.types}
    if not set(case.exception_types).issubset(authorized_types):
        raise ReviewConflictError(
            reason_code=ReasonCode.NOT_PERMITTED_BY_POLICY,
            message="The active policy does not permit approval of this case's exception type(s).",
        )
    if record is None:
        raise ReviewValidationError(
            reason_code=ReasonCode.FREE_FORM_AMOUNT_NOT_ALLOWED,
            message="No delinquency record exists for this case's account.",
        )
    if record.overdue_amount > authority.max_overdue_amount:
        raise ReviewConflictError(
            reason_code=ReasonCode.NOT_PERMITTED_BY_POLICY,
            message=(
                "The active policy does not permit approval above this reviewer role's "
                "maximum overdue amount."
            ),
        )


async def _assert_modification_eligible(
    session: AsyncSession,
    case: EscalationCaseOrm,
    request: ReviewDecisionRequest,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> None:
    """AC3: `modification_option_id` must be one of the account's current
    deterministic eligible options (`rules_engine.arrangement
    .get_eligible_options`, re-evaluated now, never trusted from whatever
    was true when the case was opened) -- never a free-form amount."""
    if not request.modification_option_id:
        raise ReviewValidationError(
            reason_code=ReasonCode.MODIFICATION_REQUIRED,
            message="MODIFY requires a modification_option_id.",
        )
    record = await _delinquency_repository.get_by_account(
        session, case.account_id, case.customer_id
    )
    if record is None:
        raise ReviewValidationError(
            reason_code=ReasonCode.FREE_FORM_AMOUNT_NOT_ALLOWED,
            message="No eligible options exist for this case's account.",
        )
    has_ptp = await has_active_pending_ptp(session, case.account_id)
    has_arrangement = await has_active_arrangement(session, case.account_id)
    result = get_eligible_options(
        policy_provider, clock, record.overdue_amount, record.dpd, has_ptp, has_arrangement
    )
    is_eligible = (
        result.ok
        and result.value is not None
        and result.value.classification is EligibilityClass.ELIGIBLE
    )
    valid_ids = (
        {option.option_id for option in result.value.options}
        if is_eligible and result.value is not None
        else set()
    )
    if request.modification_option_id not in valid_ids:
        raise ReviewValidationError(
            reason_code=ReasonCode.FREE_FORM_AMOUNT_NOT_ALLOWED,
            message="modification_option_id must be one of the account's current eligible options.",
        )


def _assert_escalate_reason_whitelisted(reason: EscalationReason | None, policy: Any) -> None:
    assert reason is not None  # noqa: S101 - _validate_shape guarantees this
    if reason not in policy.parameters.routing.reviewer_escalation_reasons:
        raise ReviewValidationError(
            reason_code=ReasonCode.ESCALATE_REASON_NOT_WHITELISTED,
            message="This reason is not permitted for a reviewer-initiated escalation.",
        )


def _target_status_for(action: ReviewAction) -> CaseStatus:
    if action is ReviewAction.REQUEST_MORE_INFORMATION:
        return CaseStatus.AWAITING_INFORMATION
    if action is ReviewAction.ESCALATE:
        return CaseStatus.RE_ROUTED
    return CaseStatus.DECIDED


def _build_audit_draft(
    case: EscalationCaseOrm,
    decision: ReviewDecisionOrm,
    correlation_id: str,
    reviewer_persona: Persona,
) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=_REVIEW_DECISION_RECORDED_EVENT_TYPE,
        actor_kind=ActorKind.STAFF,
        actor_persona=reviewer_persona,
        customer_id=case.customer_id,
        account_id=case.account_id,
        capability="escalation:review",
        policy_version=decision.policy_version,
        reason_code=decision.escalate_reason,
        final_action=decision.action,
        resource_type="review_decision",
        resource_id=decision.decision_id,
    )


def _decision_wire_dict(
    case: EscalationCaseOrm,
    decision: ReviewDecisionOrm,
    arrangement: PaymentArrangementOrm | None,
) -> dict[str, Any]:
    return {
        "decision_id": decision.decision_id,
        "case_id": decision.case_id,
        "action": decision.action,
        "reason": decision.reason,
        "note": decision.note,
        "modification_option_id": decision.modification_option_id,
        "escalate_reason": decision.escalate_reason,
        "rerouted_case_id": decision.rerouted_case_id,
        "reviewer_persona": decision.reviewer_persona,
        "decided_at": _iso_z(decision.decided_at),
        "policy_version": decision.policy_version,
        "case_status": case.status,
        "case_version": case.version,
        "arrangement": arrangement_wire_dict(arrangement) if arrangement is not None else None,
    }


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
