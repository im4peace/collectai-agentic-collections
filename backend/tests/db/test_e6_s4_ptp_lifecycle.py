"""Integration tests for `domain_services.ptp_lifecycle` against a real,
migrated Postgres database (E6-S4 AC1-AC5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.audit import queries as audit_queries
from collectai.audit.service import AuditService
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import ptp_lifecycle
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import PtpStatus
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_000123"
_CUSTOMER_ID = "cus_000101"


async def _seed_customer_and_account(
    session: AsyncSession, *, account_id: str = _ACCOUNT_ID, customer_id: str = _CUSTOMER_ID
) -> None:
    await session.execute(
        text(
            "INSERT INTO policy_rule_set (policy_version, parameters, content_hash, "
            "is_active, created_at) VALUES ('policy-v1', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :now) ON CONFLICT DO NOTHING"
        ),
        {"now": _NOW},
    )
    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name="Riley Delgado",
            email=f"{customer_id}@example.com",
            phone="+1-555-0177",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id=account_id,
            customer_id=customer_id,
            account_type="PERSONAL_LOAN",
            product_name="Everyday Personal Loan",
            currency="AED",
            opened_on=date(2025, 3, 14),
            product_attributes={
                "original_principal": "12000.00",
                "term_months": "36",
                "monthly_installment": "385.20",
            },
            created_at=_NOW,
        )
    )
    await session.commit()


def _policy_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


def _ptp_row(
    *,
    ptp_id: str,
    promised_amount: str,
    promised_date: date,
    cumulative_paid: str = "0",
    account_id: str = _ACCOUNT_ID,
    customer_id: str = _CUSTOMER_ID,
) -> PromiseToPayOrm:
    return PromiseToPayOrm(
        ptp_id=ptp_id,
        account_id=account_id,
        customer_id=customer_id,
        item_id=None,
        promised_amount=Money(promised_amount),
        promised_date=promised_date,
        status=PtpStatus.PENDING.value,
        cumulative_paid=Money(cumulative_paid),
        interaction_reference=None,
        source="CUSTOMER_CHAT",
        created_by_persona="CUSTOMER",
        created_at=_NOW,
        updated_at=_NOW,
        policy_version="policy-v1",
        version=1,
    )


def _payment_event(
    *,
    account_id: str = _ACCOUNT_ID,
    amount: str,
    outcome: str = "SUCCEEDED",
    occurred_at: datetime,
    applied_to_ptp_id: str | None,
) -> PaymentEventOrm:
    return PaymentEventOrm(
        payment_event_id=generate_id(EntityPrefix.PAYMENT_EVENT),
        account_id=account_id,
        customer_id=_CUSTOMER_ID,
        amount=Money(amount),
        outcome=outcome,
        source="CUSTOMER_CHAT",
        simulated=True,
        occurred_at=occurred_at,
        balance_after=Money("0"),
        applied_to_ptp_id=applied_to_ptp_id,
        proposal_id=None,
        created_by_persona="CUSTOMER",
    )


@pytest.mark.asyncio
async def test_qualifying_payment_reaching_promised_amount_moves_pending_to_kept(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC1."""
    await _seed_customer_and_account(session)
    clock = SimulatedClock(_NOW)
    policy = _policy_provider(clock).get_active()
    audit_service = AuditService(clock, async_sessionmaker(engine, expire_on_commit=False))

    ptp_id = generate_id(EntityPrefix.PROMISE_TO_PAY)
    ptp = _ptp_row(ptp_id=ptp_id, promised_amount="250.00", promised_date=date(2026, 10, 15))
    session.add(ptp)
    await session.flush()
    event = _payment_event(
        amount="250.00", occurred_at=_NOW, applied_to_ptp_id=ptp_id
    )
    session.add(event)
    await session.flush()

    correlation_id = uuid.uuid4().hex
    updated = await ptp_lifecycle.apply_payment_and_evaluate(
        session,
        ptp=ptp,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    await session.commit()

    assert updated.status == PtpStatus.KEPT.value
    assert updated.cumulative_paid == Money("250.00")
    assert updated.kept_at is not None

    events = await audit_queries.list_by_correlation_id(session, correlation_id)
    assert [e.event_type for e in events] == [ptp_lifecycle.PTP_KEPT_EVENT_TYPE]


@pytest.mark.asyncio
async def test_partial_payment_stays_pending_then_a_second_payment_completes_it(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC2."""
    await _seed_customer_and_account(session)
    clock = SimulatedClock(_NOW)
    policy = _policy_provider(clock).get_active()
    audit_service = AuditService(clock, async_sessionmaker(engine, expire_on_commit=False))

    ptp_id = generate_id(EntityPrefix.PROMISE_TO_PAY)
    ptp = _ptp_row(ptp_id=ptp_id, promised_amount="250.00", promised_date=date(2026, 10, 15))
    session.add(ptp)
    await session.flush()

    first_event = _payment_event(amount="100.00", occurred_at=_NOW, applied_to_ptp_id=ptp_id)
    session.add(first_event)
    await session.flush()
    after_first = await ptp_lifecycle.apply_payment_and_evaluate(
        session,
        ptp=ptp,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=uuid.uuid4().hex,
    )
    await session.commit()
    assert after_first.status == PtpStatus.PENDING.value
    assert after_first.cumulative_paid == Money("100.00")

    second_event = _payment_event(amount="150.00", occurred_at=_NOW, applied_to_ptp_id=ptp_id)
    session.add(second_event)
    await session.flush()
    correlation_id = uuid.uuid4().hex
    after_second = await ptp_lifecycle.apply_payment_and_evaluate(
        session,
        ptp=ptp,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
    )
    await session.commit()

    assert after_second.status == PtpStatus.KEPT.value
    assert after_second.cumulative_paid == Money("250.00")
    events = await audit_queries.list_by_correlation_id(session, correlation_id)
    assert [e.event_type for e in events] == [ptp_lifecycle.PTP_KEPT_EVENT_TYPE]


@pytest.mark.asyncio
async def test_failed_below_minimum_and_late_payments_do_not_count_toward_kept(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC3."""
    await _seed_customer_and_account(session)
    clock = SimulatedClock(_NOW)
    policy = _policy_provider(clock).get_active()
    audit_service = AuditService(clock, async_sessionmaker(engine, expire_on_commit=False))

    ptp_id = generate_id(EntityPrefix.PROMISE_TO_PAY)
    promised_date = date(2026, 10, 15)
    ptp = _ptp_row(ptp_id=ptp_id, promised_amount="250.00", promised_date=promised_date)
    session.add(ptp)
    await session.flush()

    # Failed outcome, below the policy's qualifying minimum (5.00), and
    # occurring after the due date -- none of these should count.
    session.add_all(
        [
            _payment_event(
                amount="250.00", outcome="FAILED", occurred_at=_NOW, applied_to_ptp_id=ptp_id
            ),
            _payment_event(amount="2.00", occurred_at=_NOW, applied_to_ptp_id=ptp_id),
            _payment_event(
                amount="250.00",
                occurred_at=datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
                applied_to_ptp_id=ptp_id,
            ),
        ]
    )
    await session.flush()

    updated = await ptp_lifecycle.apply_payment_and_evaluate(
        session,
        ptp=ptp,
        policy=policy,
        clock=clock,
        audit_service=audit_service,
        correlation_id=uuid.uuid4().hex,
    )
    await session.commit()

    assert updated.status == PtpStatus.PENDING.value
    assert updated.cumulative_paid == Money("0")


@pytest.mark.asyncio
async def test_breakage_job_breaks_overdue_unsatisfied_ptp_and_ignores_ones_not_yet_due(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC4."""
    await _seed_customer_and_account(session)
    second_account_id, second_customer_id = "acc_000456", "cus_000202"
    await _seed_customer_and_account(
        session, account_id=second_account_id, customer_id=second_customer_id
    )
    after_due = SimulatedClock(datetime(2026, 10, 16, 9, 0, tzinfo=UTC))
    policy = _policy_provider(after_due).get_active()
    audit_service = AuditService(after_due, async_sessionmaker(engine, expire_on_commit=False))

    overdue_ptp = _ptp_row(
        ptp_id=generate_id(EntityPrefix.PROMISE_TO_PAY),
        promised_amount="250.00",
        promised_date=date(2026, 10, 15),
        cumulative_paid="100.00",
    )
    not_yet_due_ptp = _ptp_row(
        ptp_id=generate_id(EntityPrefix.PROMISE_TO_PAY),
        promised_amount="250.00",
        promised_date=date(2026, 10, 30),
        account_id=second_account_id,
        customer_id=second_customer_id,
    )
    session.add_all([overdue_ptp, not_yet_due_ptp])
    await session.commit()

    result = await ptp_lifecycle.run_breakage_job(
        session,
        policy=policy,
        clock=after_due,
        audit_service=audit_service,
        correlation_id=uuid.uuid4().hex,
    )
    await session.commit()

    assert result.checked_count == 1
    assert result.broken_count == 1

    refreshed_overdue = (
        await session.execute(
            select(PromiseToPayOrm).where(PromiseToPayOrm.ptp_id == overdue_ptp.ptp_id)
        )
    ).scalar_one()
    assert refreshed_overdue.status == PtpStatus.BROKEN.value
    assert refreshed_overdue.broken_at is not None

    refreshed_not_due = (
        await session.execute(
            select(PromiseToPayOrm).where(PromiseToPayOrm.ptp_id == not_yet_due_ptp.ptp_id)
        )
    ).scalar_one()
    assert refreshed_not_due.status == PtpStatus.PENDING.value


@pytest.mark.asyncio
async def test_rerunning_the_breakage_job_does_not_retransition_or_duplicate_audit_events(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC5."""
    await _seed_customer_and_account(session)
    after_due = SimulatedClock(datetime(2026, 10, 16, 9, 0, tzinfo=UTC))
    policy = _policy_provider(after_due).get_active()
    audit_service = AuditService(after_due, async_sessionmaker(engine, expire_on_commit=False))

    ptp = _ptp_row(
        ptp_id=generate_id(EntityPrefix.PROMISE_TO_PAY),
        promised_amount="250.00",
        promised_date=date(2026, 10, 15),
    )
    session.add(ptp)
    await session.commit()

    correlation_id_1 = uuid.uuid4().hex
    first_run = await ptp_lifecycle.run_breakage_job(
        session, policy=policy, clock=after_due, audit_service=audit_service,
        correlation_id=correlation_id_1,
    )
    await session.commit()
    assert first_run.broken_count == 1

    correlation_id_2 = uuid.uuid4().hex
    second_run = await ptp_lifecycle.run_breakage_job(
        session, policy=policy, clock=after_due, audit_service=audit_service,
        correlation_id=correlation_id_2,
    )
    await session.commit()

    assert second_run.checked_count == 0
    assert second_run.broken_count == 0

    events_1 = await audit_queries.list_by_correlation_id(session, correlation_id_1)
    events_2 = await audit_queries.list_by_correlation_id(session, correlation_id_2)
    assert len(events_1) == 1
    assert len(events_2) == 0

    refreshed = (
        await session.execute(select(PromiseToPayOrm).where(PromiseToPayOrm.ptp_id == ptp.ptp_id))
    ).scalar_one()
    assert refreshed.status == PtpStatus.BROKEN.value
