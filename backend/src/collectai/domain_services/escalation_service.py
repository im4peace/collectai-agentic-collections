"""Escalation case creation (E7-S1).

NOTE: nearing the code-gen skill's 300-line warning threshold. The
staff-facing list query already lives in the sibling
`_escalation_queue_query.py`; if this module grows further, split the
idempotency-key creation path (`_create_with_idempotency_key`) into its own
submodule next.

Creates `EscalationCase` rows transactionally with their audit event, for
every trigger BRD 7.1/scenarios 12-13-21 describe: the AI proposing
escalation, the customer asking for a human, or a sensitive intent/safety
signal/special request. Destination (`queue`, `reviewer_role`) and
`priority` come only from `rules_engine.routing.route_escalation` (AC2) --
this module never accepts them as parameters, mirroring that service's own
"never a `queue`/`reviewer_role` parameter" contract.

`create_escalation` is generic over every `EscalationReason` (AC1's full
list), but this group (Group G) wires only two call sites into it:
`application.chat_flow`'s REQUEST_HUMAN (immediate) and UNRESOLVED_UNKNOWN
(third consecutive UNKNOWN) paths, plus `application.confirmation_flow`'s
AMBIGUOUS_VALIDATION path on confirm. The other reasons this function
already supports (FINANCIAL_HARDSHIP, DISPUTE, VULNERABLE_CUSTOMER,
SETTLEMENT_REQUEST, POLICY_EXCEPTION, EXCEPTIONAL_ARRANGEMENT,
HIGH_RISK_COMPLIANCE) are wired by later stories (E7-S4, E8-S1, E8-S2,
E8-S3) that create their own linked hardship/dispute/exception records
first -- `_chat_escalation_reporting.report_escalation`'s
`ESCALATION_REQUIRED` audit-only signal still covers those reasons in this
group, unchanged.

AC5 ("creating an escalation sets automated_treatment_suppressed ... until a
human decision") needs no extra bookkeeping here: `rules_engine.suppression
.evaluate_suppression` (E2-S4) already derives `automated_treatment_suppressed`
live from "does an OPEN-or-not-DECIDED EscalationCase exist for this
account" (`application._tool_backend_suppression.build_suppression_input`,
`domain_services.customer360_service._derive_treatment_facts`) -- inserting
the OPEN row here is the entire mechanism; no separate suppression flag or
table exists to set (data-models.md section 1: "Derived values are not
stored").
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.rules_engine.routing import RoutingResult, route_escalation
from collectai.types.clock import Clock
from collectai.types.enums import ActorKind, AuditStage, CaseSource, CaseStatus, EscalationReason
from collectai.types.ids import EntityPrefix, generate_id

ESCALATION_CASE_CREATED_EVENT_TYPE = "ESCALATION_CASE_CREATED"

_OPEN_CASE_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.OPEN, CaseStatus.IN_REVIEW, CaseStatus.AWAITING_INFORMATION}
)

_SUMMARY_TEMPLATES: dict[EscalationReason, str] = {
    EscalationReason.REQUEST_HUMAN: "Customer asked to speak with a human colleague.",
    EscalationReason.UNRESOLVED_UNKNOWN: "Chat could not resolve the customer's request.",
    EscalationReason.AI_FAILURE_FALLBACK: (
        "AI assistant was unavailable or reached its tool-call limit."
    ),
    EscalationReason.EXCEPTIONAL_ARRANGEMENT: (
        "Customer requested an exceptional payment arrangement."
    ),
    EscalationReason.FINANCIAL_HARDSHIP: "Customer reported financial hardship.",
    EscalationReason.DISPUTE: "Customer disputes an amount or item.",
    EscalationReason.SETTLEMENT_REQUEST: "Customer requested a settlement.",
    EscalationReason.AMBIGUOUS_VALIDATION: "A confirmation could not be automatically authorized.",
    EscalationReason.VULNERABLE_CUSTOMER: "A customer vulnerability signal was detected.",
    EscalationReason.POLICY_EXCEPTION: "Customer requested an exception to normal policy.",
    EscalationReason.HIGH_RISK_COMPLIANCE: "Case flagged for compliance review.",
}


@dataclass(frozen=True, slots=True)
class EscalationCreationResult:
    case: EscalationCaseOrm
    created: bool
    """False when an existing OPEN/IN_REVIEW/AWAITING_INFORMATION case for
    the same `(conversation_id, reason)`, or the same idempotency key, was
    returned instead of a new row (AC6)."""


async def create_escalation(
    session: AsyncSession,
    *,
    reason: EscalationReason,
    customer_id: str,
    account_id: str,
    conversation_id: str | None,
    item_id: str | None,
    source: CaseSource,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    idempotency_service: IdempotencyService | None = None,
    idempotency_key: str | None = None,
    summary: str | None = None,
    parent_case_id: str | None = None,
    dispute_id: str | None = None,
) -> EscalationCreationResult:
    """AC1, AC2, AC4, AC6. Writes the case and its audit event in this
    caller's transaction: a flush failure (e.g. `AuditUnavailable`
    propagating from `record_in`) rolls back the whole thing, so a failed
    escalation write never leaves a case without its audit event (AC4).
    `parent_case_id` (E7-S2, Group H): the case this one was re-routed from,
    via a reviewer's ESCALATE action -- `None` for every other trigger.
    `dispute_id` (E8-S3, Group H): the `Dispute` this case was opened for,
    if any -- `None` for every other trigger."""
    existing = await _find_open_duplicate(session, conversation_id, reason)
    if existing is not None:
        return EscalationCreationResult(case=existing, created=False)

    if idempotency_key is not None and idempotency_service is not None:
        return await _create_with_idempotency_key(
            session,
            reason=reason,
            customer_id=customer_id,
            account_id=account_id,
            conversation_id=conversation_id,
            item_id=item_id,
            source=source,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            idempotency_service=idempotency_service,
            idempotency_key=idempotency_key,
            summary=summary,
            parent_case_id=parent_case_id,
            dispute_id=dispute_id,
        )

    case = await _insert_case(
        session,
        reason=reason,
        customer_id=customer_id,
        account_id=account_id,
        conversation_id=conversation_id,
        item_id=item_id,
        source=source,
        policy_provider=policy_provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        summary=summary,
        parent_case_id=parent_case_id,
        dispute_id=dispute_id,
    )
    return EscalationCreationResult(case=case, created=True)


async def _find_open_duplicate(
    session: AsyncSession, conversation_id: str | None, reason: EscalationReason
) -> EscalationCaseOrm | None:
    """AC6: "a second trigger for the same conversation and reason while a
    case is OPEN returns the existing case". Applies only when
    `conversation_id` is known (a reviewer-initiated case has none)."""
    if conversation_id is None:
        return None
    stmt = select(EscalationCaseOrm).where(
        EscalationCaseOrm.conversation_id == conversation_id,
        EscalationCaseOrm.reason == reason.value,
        EscalationCaseOrm.status.in_([status.value for status in _OPEN_CASE_STATUSES]),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _create_with_idempotency_key(
    session: AsyncSession,
    *,
    reason: EscalationReason,
    customer_id: str,
    account_id: str,
    conversation_id: str | None,
    item_id: str | None,
    source: CaseSource,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    idempotency_service: IdempotencyService,
    idempotency_key: str,
    summary: str | None,
    parent_case_id: str | None,
    dispute_id: str | None = None,
) -> EscalationCreationResult:
    """AC6's other clause: "the same idempotency key ... returns the
    existing case and creates no duplicate", used by the `POST .../handoff`
    endpoint's required `Idempotency-Key` header."""
    created_flag = {"created": True}

    async def _compute() -> dict[str, object]:
        case = await _insert_case(
            session,
            reason=reason,
            customer_id=customer_id,
            account_id=account_id,
            conversation_id=conversation_id,
            item_id=item_id,
            source=source,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            summary=summary,
            parent_case_id=parent_case_id,
            dispute_id=dispute_id,
        )
        return {"case_id": case.case_id}

    body, replayed = await idempotency_service.get_or_create(
        session,
        scope="escalation_case",
        key=idempotency_key,
        request_hash=f"{conversation_id}:{reason.value}",
        resource_type="escalation_case",
        resource_id=None,
        compute_response=_compute,
    )
    created_flag["created"] = not replayed
    case_id = body["case_id"]
    assert isinstance(case_id, str)  # noqa: S101 - always the id this module itself wrote
    case = await session.get(EscalationCaseOrm, case_id)
    assert case is not None  # noqa: S101 - the id came from a row this same transaction wrote
    return EscalationCreationResult(case=case, created=created_flag["created"])


async def _insert_case(
    session: AsyncSession,
    *,
    reason: EscalationReason,
    customer_id: str,
    account_id: str,
    conversation_id: str | None,
    item_id: str | None,
    source: CaseSource,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    summary: str | None,
    parent_case_id: str | None = None,
    dispute_id: str | None = None,
) -> EscalationCaseOrm:
    routing = route_escalation(reason, policy_provider)
    now = clock.now()
    case = EscalationCaseOrm(
        case_id=generate_id(EntityPrefix.ESCALATION_CASE),
        customer_id=customer_id,
        account_id=account_id,
        conversation_id=conversation_id,
        item_id=item_id,
        reason=reason.value,
        queue=routing.queue.value,
        reviewer_role=routing.reviewer_role.value,
        priority=routing.priority.value,
        status=CaseStatus.OPEN.value,
        source=source.value,
        summary=summary or _SUMMARY_TEMPLATES[reason],
        requested_terms=None,
        exception_types=None,
        hardship_case_id=None,
        dispute_id=dispute_id,
        recommendation_id=None,
        parent_case_id=parent_case_id,
        rerouted_to_case_id=None,
        routing_policy_version=routing.policy_version,
        routing_flags=list(routing.flags),
        first_reviewed_at=None,
        created_at=now,
        decided_at=None,
        updated_at=now,
        version=1,
    )
    session.add(case)
    await session.flush()
    await audit_service.record_in(session, _build_audit_draft(case, routing, correlation_id))
    return case


def _build_audit_draft(
    case: EscalationCaseOrm, routing: RoutingResult, correlation_id: str
) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type=ESCALATION_CASE_CREATED_EVENT_TYPE,
        actor_kind=ActorKind.SYSTEM,
        customer_id=case.customer_id,
        account_id=case.account_id,
        policy_version=routing.policy_version,
        rule_results={
            "queue": routing.queue.value,
            "reviewer_role": routing.reviewer_role.value,
            "priority": routing.priority.value,
            "routing_flags": list(routing.flags),
        },
        reason_code=case.reason,
        final_action="ESCALATION_CASE_CREATED",
        resource_type="escalation_case",
        resource_id=case.case_id,
    )


