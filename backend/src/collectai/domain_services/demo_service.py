"""Dev and demo controls (E9-S3; api-contracts.md 3.14).

Five operations, all gated by `settings.demo_controls_enabled` at the router
layer (never here -- this module has no opinion on the flag, matching
`review_service`'s "authorization is the router/dependency's job, this
module does the domain work" split):

- `build_demo_state` -- read-only: LLM mode, clock, active policy version.
- `advance_clock` -- moves the installed `Clock` forward (only meaningful
  when `api/app.py`'s `create_app` installed a `SimulatedClock`, which it
  does exactly when `demo_controls_enabled` is true and no explicit clock
  was given -- see that module's own docstring).
- `run_ptp_lifecycle` -- reruns `ptp_lifecycle.run_breakage_job`, the same
  job the scheduler runs (AC2's "subsequent breakage run marks due PTPs
  BROKEN").
- `simulate_payment` -- records a `PaymentEvent` via the same
  `payment_service.record_simulated_payment` the chat confirmation path
  uses, with `source=DEMO_CONTROL` (AC3), then re-evaluates any PENDING PTP
  the same way `application._confirmation_apply` does for a real payment.
- `reseed` -- restores the seeded dataset's core tables. Deliberately an
  UPDATE-based reset (`CustomerScopedRepository.bulk_upsert_update_on_
  conflict`), never a `DELETE` + re-`INSERT`: `collectai_app` holds no
  `DELETE` grant on any table (`deploy/db/init-roles.sql`), and this module
  never weakens that -- see `reseed`'s own docstring for the exact
  restored/not-restored table split.

Every write here records its own `DEMO_*` audit event (AC4), in addition to
any per-row audit events the reused domain service (`ptp_lifecycle`,
`payment_service`) already writes for its own transitions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import payment_service, ptp_lifecycle
from collectai.domain_services._demo_exceptions import (
    DemoAccountNotFoundError,
    DemoValidationError,
)
from collectai.domain_services._ptp_helpers import ptp_wire_dict
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.delinquent_item_repository import DelinquentItemRepository
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.persistence.repositories.interaction_repository import InteractionRepository
from collectai.persistence.repositories.promise_to_pay_repository import PromiseToPayRepository
from collectai.persistence.seed.generator import (
    DEFAULT_ACCOUNT_COUNT,
    DEFAULT_RANDOM_SEED,
    generate_seed_dataset,
)
from collectai.types.clock import Clock, SimulatedClock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    ClockMode,
    LlmMode,
    PaymentOutcome,
    PaymentSource,
    Persona,
)
from collectai.types.money import Money, MoneyValidationError
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

DEMO_CLOCK_ADVANCED_EVENT_TYPE = "DEMO_CLOCK_ADVANCED"
DEMO_PTP_LIFECYCLE_RUN_EVENT_TYPE = "DEMO_PTP_LIFECYCLE_RUN"
DEMO_RESEED_EVENT_TYPE = "DEMO_RESEED"
_DEMO_CONTROLS_CAPABILITY = "demo_controls:use"
_SIMULATE_PAYMENT_SCOPE = "demo_simulate_payment"

_account_repository = AccountRepository()
_delinquency_repository = DelinquencyRecordRepository()
_idempotency_repository = IdempotencyRepository()


def clock_info(clock: Clock) -> dict[str, object]:
    mode = ClockMode.SIMULATED if isinstance(clock, SimulatedClock) else ClockMode.SYSTEM
    return {"mode": mode.value, "current_time": _iso_z(clock.now())}


def build_demo_state(
    *,
    clock: Clock,
    llm_mode: LlmMode,
    demo_controls_enabled: bool,
    policy_provider: PolicyProvider,
) -> dict[str, object]:
    try:
        policy_version: str | None = policy_provider.get_active().policy_version
    except PolicyUnavailable:
        policy_version = None
    return {
        "llm_mode": llm_mode.value,
        "clock": clock_info(clock),
        "demo_controls_enabled": demo_controls_enabled,
        "policy_version": policy_version,
    }


async def advance_clock(
    session: AsyncSession,
    *,
    clock: Clock,
    days: int,
    reviewer_persona: Persona,
    audit_service: AuditService,
    correlation_id: str,
) -> dict[str, object]:
    """AC2: moves the installed `Clock` forward by `days`. `refresh_snapshots`
    (api-contracts.md's optional DPD/bucket/`as_of` re-sync) is accepted by
    the router but is a documented no-op here -- no core-sync/snapshot-
    recompute service exists anywhere in this codebase yet (not a Group I
    dependency, and out of E9-S3's own numbered acceptance criteria, which
    only require the clock to move and a subsequent breakage run to see the
    new date -- both true without it)."""
    assert isinstance(clock, SimulatedClock)  # noqa: S101 - only reachable when the flag installed one
    clock.advance(days)
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=DEMO_CLOCK_ADVANCED_EVENT_TYPE,
            actor_kind=ActorKind.STAFF,
            actor_persona=reviewer_persona,
            capability=_DEMO_CONTROLS_CAPABILITY,
            final_action=DEMO_CLOCK_ADVANCED_EVENT_TYPE,
            rule_results={"days": days},
        ),
    )
    return {"clock": clock_info(clock), "snapshots_refreshed": 0}


async def run_ptp_lifecycle(
    session: AsyncSession,
    *,
    policy_provider: PolicyProvider,
    clock: Clock,
    reviewer_persona: Persona,
    audit_service: AuditService,
    correlation_id: str,
) -> dict[str, object]:
    """AC2: the same job the scheduler runs (`ptp_lifecycle.run_breakage_job`
    -- see `jobs.ptp_lifecycle_job`). Safe to rerun (that module's own
    docstring: only PENDING rows are ever selected)."""
    policy = policy_provider.get_active()
    result = await ptp_lifecycle.run_breakage_job(
        session,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=DEMO_PTP_LIFECYCLE_RUN_EVENT_TYPE,
            actor_kind=ActorKind.STAFF,
            actor_persona=reviewer_persona,
            capability=_DEMO_CONTROLS_CAPABILITY,
            final_action=DEMO_PTP_LIFECYCLE_RUN_EVENT_TYPE,
            rule_results={
                "evaluated": result.checked_count,
                "kept": result.kept_count,
                "broken": result.broken_count,
            },
        ),
    )
    unchanged = result.checked_count - result.kept_count - result.broken_count
    return {
        "evaluated": result.checked_count,
        "kept": result.kept_count,
        "broken": result.broken_count,
        "unchanged": unchanged,
    }


async def simulate_payment(
    session: AsyncSession,
    *,
    account_id: str,
    amount_input: str,
    outcome: PaymentOutcome,
    reviewer_persona: Persona,
    idempotency_key: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> tuple[dict[str, object], bool]:
    """AC3: records a `PaymentEvent` with `source=DEMO_CONTROL`,
    `simulated=True`, via the same `payment_service.record_simulated_payment`
    the chat confirmation path uses, then re-evaluates any PENDING PTP for
    the account exactly as `application._confirmation_apply` does. Returns
    `(response_body, replayed)`. `request_hash` is a SHA256 hex digest
    (matching `review_service._hash_request`'s own convention) -- migration
    0006's `idempotency_record.request_hash` column is `char(64)`, sized
    exactly for a hex digest; a raw, shorter canonical string would come
    back blank-padded by Postgres on the next read and never compare equal
    to a freshly computed one again."""
    request_hash = hashlib.sha256(
        f"{account_id}:{amount_input}:{outcome.value}".encode()
    ).hexdigest()
    existing = await _idempotency_repository.get_by_scope_and_key(
        session, _SIMULATE_PAYMENT_SCOPE, idempotency_key
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise DemoValidationError(
                reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
                message="This idempotency key was already used for a different request.",
            )
        return existing.response_body, True

    account = await _account_repository.get_by_id(session, account_id)
    if account is None:
        raise DemoAccountNotFoundError(account_id)
    record = await _delinquency_repository.get_by_account(session, account_id, account.customer_id)
    if record is None:
        raise DemoAccountNotFoundError(account_id)

    amount = _validate_amount(amount_input, record)
    pending_ptp = await ptp_lifecycle.find_pending_ptp_for_account(session, account_id)

    event = await payment_service.record_simulated_payment(
        session,
        record=record,
        amount=amount,
        proposal_id=None,
        correlation_id=correlation_id,
        clock=clock,
        audit_service=audit_service,
        persona=reviewer_persona,
        applied_to_ptp_id=pending_ptp.ptp_id if pending_ptp is not None else None,
        source=PaymentSource.DEMO_CONTROL,
        outcome=outcome,
    )

    ptp_after: dict[str, object] | None = None
    if pending_ptp is not None:
        policy = policy_provider.get_active()
        updated_ptp = await ptp_lifecycle.apply_payment_and_evaluate(
            session,
            ptp=pending_ptp,
            policy=policy,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
        )
        ptp_after = ptp_wire_dict(updated_ptp)

    response_body: dict[str, object] = {
        "payment_event": payment_service.payment_event_wire_dict(event),
        "ptp": ptp_after,
    }

    async def _already_computed() -> dict[str, object]:
        return response_body

    stored_body, _ = await IdempotencyService(clock).get_or_create(
        session,
        scope=_SIMULATE_PAYMENT_SCOPE,
        key=idempotency_key,
        request_hash=request_hash,
        resource_type="payment_event",
        resource_id=event.payment_event_id,
        compute_response=_already_computed,
    )
    return stored_body, False


def _validate_amount(amount_input: str, record: DelinquencyRecordOrm) -> Money:
    try:
        amount = Money(amount_input)
    except MoneyValidationError as exc:
        raise DemoValidationError(reason_code=exc.reason_code, message=str(exc)) from exc
    if amount.amount == 0:
        raise DemoValidationError(
            reason_code=ReasonCode.ZERO_AMOUNT, message="amount must be greater than zero."
        )
    if amount > record.outstanding_balance:
        raise DemoValidationError(
            reason_code=ReasonCode.OVER_BALANCE,
            message="amount must not exceed the account's outstanding balance.",
        )
    return amount


@dataclass(frozen=True, slots=True)
class ReseedResult:
    customers: int
    accounts: int
    delinquency_records: int
    delinquent_items: int
    interactions: int
    promise_to_pays: int


async def reseed(
    session: AsyncSession,
    *,
    reviewer_persona: Persona,
    audit_service: AuditService,
    correlation_id: str,
) -> ReseedResult:
    """AC4: restores the seeded dataset's core tables (customer, account,
    delinquency_record, delinquent_item, interaction, promise_to_pay) to
    their deterministically-generated seed values, via `UPDATE` (this
    module's own docstring explains why never `DELETE`). Rows in every
    other table (escalation_case, dispute, hardship_case,
    payment_arrangement, payment_event, conversation, chat_turn,
    chat_message, proposal, recommendation, review_decision,
    idempotency_record) created during the demo session are never deleted
    -- `collectai_app` cannot delete them, and this module does not attempt
    to. Uses the exact same `(account_count, random_seed)` as `bootstrap.cli
    run_seed`'s own defaults, so ids and values match what a fresh `seed`
    CLI run would have produced."""
    dataset = generate_seed_dataset(
        account_count=DEFAULT_ACCOUNT_COUNT, random_seed=DEFAULT_RANDOM_SEED
    )
    customer_repository = CustomerRepository()
    account_repository = AccountRepository()
    delinquent_item_repository = DelinquentItemRepository()
    interaction_repository = InteractionRepository()
    promise_to_pay_repository = PromiseToPayRepository()

    counts = ReseedResult(
        customers=await customer_repository.bulk_upsert_update_on_conflict(
            session, dataset.customers
        ),
        accounts=await account_repository.bulk_upsert_update_on_conflict(
            session, dataset.accounts, pk_columns=["account_id"]
        ),
        delinquency_records=await _delinquency_repository.bulk_upsert_update_on_conflict(
            session, dataset.delinquency_records, pk_columns=["account_id"]
        ),
        delinquent_items=await delinquent_item_repository.bulk_upsert_update_on_conflict(
            session, dataset.delinquent_items, pk_columns=["item_id"]
        ),
        interactions=await interaction_repository.bulk_upsert_update_on_conflict(
            session, dataset.interactions, pk_columns=["interaction_id"]
        ),
        promise_to_pays=await promise_to_pay_repository.bulk_upsert_update_on_conflict(
            session, dataset.promise_to_pays, pk_columns=["ptp_id"]
        ),
    )
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=DEMO_RESEED_EVENT_TYPE,
            actor_kind=ActorKind.STAFF,
            actor_persona=reviewer_persona,
            capability=_DEMO_CONTROLS_CAPABILITY,
            final_action=DEMO_RESEED_EVENT_TYPE,
        ),
    )
    return counts


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
