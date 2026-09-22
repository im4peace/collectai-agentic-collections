"""Integration test for `refresh_and_check` (E2-S5 AC5) against a real,
migrated Postgres database -- proves the ORM mapping and the real
`DelinquencyRecordRepository` query actually wire together, not just the
mocked double in `tests/unit/domain_services/test_e2_s5_snapshot_service.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.snapshot_service import refresh_and_check
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.types.clock import SimulatedClock
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def _seed_customer_account_and_record(
    session: AsyncSession,
    *,
    customer_id: str,
    account_id: str,
    record_version: int = 7,
    dpd: int = 34,
    bucket: str = "DPD_30_59",
) -> None:
    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name="Riley Delgado",
            email="riley.delgado@example.com",
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
            currency="USD",
            opened_on=date(2025, 3, 14),
            product_attributes={
                "original_principal": "12000.00",
                "term_months": "36",
                "monthly_installment": "385.20",
            },
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=account_id,
            customer_id=customer_id,
            outstanding_balance=Money("8420.10"),
            overdue_amount=Money("770.40"),
            dpd=dpd,
            bucket=bucket,
            collection_status="IN_PROGRESS",
            as_of=_NOW,
            record_version=record_version,
            updated_at=_NOW,
        )
    )
    await session.commit()


def _active_policy_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


@pytest.mark.asyncio
async def test_fresh_consistent_snapshot_succeeds_against_real_database(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_customer_account_and_record(
        session, customer_id="cus_000201", account_id="acc_000301"
    )
    clock = SimulatedClock(_NOW)

    result = await refresh_and_check(
        session,
        account_id="acc_000301",
        customer_id="cus_000201",
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.current_record.outstanding_balance == Money("8420.10")
    assert result.value.consistency.consistent is True


@pytest.mark.asyncio
async def test_stale_snapshot_against_real_database_returns_failure(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_customer_account_and_record(
        session, customer_id="cus_000202", account_id="acc_000302"
    )
    later = datetime(2026, 10, 1, 10, 30, tzinfo=UTC)
    clock = SimulatedClock(later)

    result = await refresh_and_check(
        session,
        account_id="acc_000302",
        customer_id="cus_000202",
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.STALE_DATA


@pytest.mark.asyncio
async def test_no_delinquency_record_against_real_database_returns_failure(
    session: AsyncSession, clean_db: None
) -> None:
    """No `DelinquencyRecordOrm` seeded for this account: 404-equivalent,
    handled as a failure result rather than a crash."""
    session.add(
        CustomerOrm(
            customer_id="cus_000203",
            display_name="Jordan Okafor",
            email="jordan.okafor@example.com",
            phone="+1-555-0188",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.commit()
    clock = SimulatedClock(_NOW)

    result = await refresh_and_check(
        session,
        account_id="acc_000303",
        customer_id="cus_000203",
        snapshot_as_of=_NOW,
        snapshot_version=1,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.AMBIGUOUS_VALIDATION


@pytest.mark.asyncio
async def test_inconsistent_record_against_real_database_returns_failure(
    session: AsyncSession, clean_db: None
) -> None:
    """dpd=34 seeded with bucket=CURRENT: an internally inconsistent record."""
    await _seed_customer_account_and_record(
        session,
        customer_id="cus_000204",
        account_id="acc_000304",
        dpd=34,
        bucket="CURRENT",
    )
    clock = SimulatedClock(_NOW)

    result = await refresh_and_check(
        session,
        account_id="acc_000304",
        customer_id="cus_000204",
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.INCONSISTENT_RECORD
