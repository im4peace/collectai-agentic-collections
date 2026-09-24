"""PTP lifecycle: KEPT and BROKEN transitions (E6-S4).

Two entry points, one shared evaluator:

- `apply_payment_and_evaluate` -- called once, synchronously, right after a
  new `PaymentEvent` is recorded against an account that has a PENDING PTP
  (`application._confirmation_apply._confirm_payment`). Re-evaluates that
  PTP's satisfaction immediately, so a payment that completes the promised
  amount moves PENDING to KEPT the same turn (AC1, AC2).
- `run_breakage_job` -- a separate, explicitly-invoked batch pass (see
  `collectai.jobs.ptp_lifecycle_job`) that moves every PENDING PTP whose due
  date has passed without satisfaction to BROKEN (AC4). Never called inline
  from the chat/payment path: AC1/AC2 only ever produce KEPT in real time,
  matching the story's own split between "a payment satisfies" and "time
  passes without satisfaction."

Both call `_evaluate_and_apply`, which wraps the already-deterministic,
already-tested `rules_engine.ptp_rules.evaluate_satisfaction` (E2-S2) -- this
module owns no satisfaction math of its own, only the persistence/audit
orchestration around that pure function, and the transition guard (AC6).

`payment_event` is one of `deploy/db/init-roles.sql`'s insert-only tables
(`collectai_app` holds no UPDATE grant): unlike an early draft of this
story, `applied_to_ptp_id` is never back-filled with an UPDATE after the
fact. The caller must already know which PTP (if any) a payment applies to
*before* the row is inserted and pass it to
`domain_services.payment_service.record_simulated_payment` as
`applied_to_ptp_id` at INSERT time -- see that function's own docstring.
`promise_to_pay`, by contrast, is an ordinary INSERT/SELECT/UPDATE table, so
its own status/cumulative_paid transition here is a normal UPDATE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.models import PolicyRuleSet
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.ptp_rules import evaluate_satisfaction
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    PaymentOutcome,
    PaymentSource,
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.models import PaymentEvent as PaymentEventModel
from collectai.types.models import PromiseToPay as PromiseToPayModel
from collectai.types.money import Money

PTP_KEPT_EVENT_TYPE = "PTP_KEPT"
PTP_BROKEN_EVENT_TYPE = "PTP_BROKEN"

# AC6: the only transitions this module (or any caller) may ever persist.
# CANCELLED is listed for completeness (data-models.md's full lifecycle) even
# though nothing in this story writes it; a future officer-cancel story is
# the only other writer of PENDING -> CANCELLED, and must reuse this guard.
_ALLOWED_TRANSITIONS: frozenset[tuple[PtpStatus, PtpStatus]] = frozenset(
    {
        (PtpStatus.PENDING, PtpStatus.KEPT),
        (PtpStatus.PENDING, PtpStatus.BROKEN),
        (PtpStatus.PENDING, PtpStatus.CANCELLED),
    }
)


class InvalidPtpTransitionError(Exception):
    """AC6: a transition outside `_ALLOWED_TRANSITIONS` was attempted."""

    def __init__(self, *, current: PtpStatus, target: PtpStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition a PTP from {current.value} to {target.value}.")


def validate_ptp_transition(current: PtpStatus, target: PtpStatus) -> None:
    """Raise `InvalidPtpTransitionError` unless `(current, target)` is one of
    the state machine's allowed edges. Pure, no I/O -- callable directly by
    tests without a database."""
    if current is target:
        return
    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidPtpTransitionError(current=current, target=target)


@dataclass(frozen=True, slots=True)
class BreakageJobResult:
    checked_count: int
    broken_count: int
    kept_count: int
    """PTPs the job itself found already-satisfied when it ran (defensive:
    the real-time path is the normal way a PTP reaches KEPT, but the job
    reuses the same evaluator, so it never mis-classifies a satisfied PTP as
    BROKEN just because it runs after the due date -- AC1 takes precedence
    over AC4 for any single PTP)."""


async def find_pending_ptp_for_account(
    session: AsyncSession, account_id: str
) -> PromiseToPayOrm | None:
    """At most one PENDING PTP can exist per account (enforced by
    `_ptp_helpers.has_active_pending_ptp`'s own conflict check at creation
    time), so this is safe to treat as unique."""
    stmt = select(PromiseToPayOrm).where(
        PromiseToPayOrm.account_id == account_id,
        PromiseToPayOrm.status == PtpStatus.PENDING.value,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def apply_payment_and_evaluate(
    session: AsyncSession,
    *,
    ptp: PromiseToPayOrm,
    policy: PolicyRuleSet,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PromiseToPayOrm:
    """Re-evaluate `ptp` right after a new qualifying-candidate `PaymentEvent`
    was inserted against it (`applied_to_ptp_id` already set at INSERT time
    by the caller). AC1/AC2: only ever persists KEPT or leaves PENDING with
    an updated `cumulative_paid` -- never BROKEN (that is `run_breakage_job`'s
    sole responsibility, AC4)."""
    return await _evaluate_and_apply(
        session,
        ptp=ptp,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        allow_broken=False,
    )


async def run_breakage_job(
    session: AsyncSession,
    *,
    policy: PolicyRuleSet,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> BreakageJobResult:
    """AC4/AC5: move every PENDING PTP whose due date has passed to BROKEN
    unless its cumulative qualifying amount already satisfies it, and never
    touch a PTP whose due date has not yet passed. Safe to rerun: only
    PENDING rows are ever selected, so an already-BROKEN/KEPT row from a
    prior run is invisible to a later run and cannot be re-transitioned or
    double-audited."""
    today: date = clock.now().date()
    stmt = select(PromiseToPayOrm).where(
        PromiseToPayOrm.status == PtpStatus.PENDING.value,
        PromiseToPayOrm.promised_date < today,
    )
    due_ptps = (await session.execute(stmt)).scalars().all()

    broken_count = 0
    kept_count = 0
    for ptp in due_ptps:
        updated = await _evaluate_and_apply(
            session,
            ptp=ptp,
            policy=policy,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            allow_broken=True,
        )
        if updated.status == PtpStatus.BROKEN.value:
            broken_count += 1
        elif updated.status == PtpStatus.KEPT.value:
            kept_count += 1
    return BreakageJobResult(
        checked_count=len(due_ptps), broken_count=broken_count, kept_count=kept_count
    )


async def _evaluate_and_apply(
    session: AsyncSession,
    *,
    ptp: PromiseToPayOrm,
    policy: PolicyRuleSet,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    allow_broken: bool,
) -> PromiseToPayOrm:
    if ptp.status != PtpStatus.PENDING.value:
        # AC5: a KEPT/BROKEN/CANCELLED PTP is never re-evaluated -- this is
        # what makes replaying a payment event or rerunning the breakage job
        # a true no-op rather than merely "no audit event written".
        return ptp

    events = await _qualifying_candidate_events(session, ptp.ptp_id)
    outcome = evaluate_satisfaction(_to_domain_ptp(ptp), events, policy, clock)

    if outcome.status is PtpStatus.KEPT:
        return await _transition(
            session,
            ptp=ptp,
            target=PtpStatus.KEPT,
            cumulative_paid=outcome.cumulative_paid,
            event_type=PTP_KEPT_EVENT_TYPE,
            timestamp_field="kept_at",
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
    if outcome.status is PtpStatus.BROKEN and allow_broken:
        return await _transition(
            session,
            ptp=ptp,
            target=PtpStatus.BROKEN,
            cumulative_paid=outcome.cumulative_paid,
            event_type=PTP_BROKEN_EVENT_TYPE,
            timestamp_field="broken_at",
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )

    # Still PENDING (or BROKEN-eligible but this caller may not persist it,
    # e.g. AC1's real-time path evaluated a same-day payment past the
    # policy's own PTP window edge): only the cumulative amount may change.
    if outcome.cumulative_paid != ptp.cumulative_paid:
        ptp.cumulative_paid = outcome.cumulative_paid
        ptp.updated_at = clock.now()
        await session.flush()
    return ptp


async def _transition(
    session: AsyncSession,
    *,
    ptp: PromiseToPayOrm,
    target: PtpStatus,
    cumulative_paid: Money,
    event_type: str,
    timestamp_field: str,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PromiseToPayOrm:
    validate_ptp_transition(PtpStatus(ptp.status), target)
    now = clock.now()
    ptp.status = target.value
    ptp.cumulative_paid = cumulative_paid
    ptp.updated_at = now
    ptp.version += 1
    setattr(ptp, timestamp_field, now)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=event_type,
            actor_kind=ActorKind.SYSTEM,
            actor_persona=Persona.CUSTOMER,
            customer_id=ptp.customer_id,
            account_id=ptp.account_id,
            policy_version=ptp.policy_version,
            final_action=event_type,
            resource_type="promise_to_pay",
            resource_id=ptp.ptp_id,
        ),
    )
    return ptp


async def _qualifying_candidate_events(
    session: AsyncSession, ptp_id: str
) -> list[PaymentEventModel]:
    """Every `PaymentEvent` already applied to `ptp_id`, regardless of
    outcome/amount/date -- `evaluate_satisfaction` itself does the
    SUCCEEDED/min-amount/on-or-before-due-date filtering (AC3), so this is
    deliberately unfiltered beyond the FK match."""
    stmt = select(PaymentEventOrm).where(PaymentEventOrm.applied_to_ptp_id == ptp_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_domain_event(row) for row in rows]


def _to_domain_ptp(row: PromiseToPayOrm) -> PromiseToPayModel:
    return PromiseToPayModel(
        ptp_id=row.ptp_id,
        account_id=row.account_id,
        customer_id=row.customer_id,
        item_id=row.item_id,
        promised_amount=row.promised_amount,
        promised_date=row.promised_date,
        status=PtpStatus(row.status),
        cumulative_paid=row.cumulative_paid,
        interaction_reference=row.interaction_reference,
        source=PtpSource(row.source),
        created_by_persona=Persona(row.created_by_persona),
        created_at=row.created_at,
        updated_at=row.updated_at,
        kept_at=row.kept_at,
        broken_at=row.broken_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
        policy_version=row.policy_version,
        version=row.version,
    )


def _to_domain_event(row: PaymentEventOrm) -> PaymentEventModel:
    return PaymentEventModel(
        payment_event_id=row.payment_event_id,
        account_id=row.account_id,
        customer_id=row.customer_id,
        amount=row.amount,
        outcome=PaymentOutcome(row.outcome),
        source=PaymentSource(row.source),
        simulated=True,  # DB CHECK (simulated) guarantees this always holds
        occurred_at=row.occurred_at,
        balance_after=row.balance_after,
        applied_to_ptp_id=row.applied_to_ptp_id,
        proposal_id=row.proposal_id,
        created_by_persona=Persona(row.created_by_persona),
    )
