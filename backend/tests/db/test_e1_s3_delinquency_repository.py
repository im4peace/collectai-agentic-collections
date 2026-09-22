"""AC2 (Money round-trip through the repository) and AC7 (DelinquencyRecord
`as_of` + monotonically increasing `record_version`, every update
increments it, including via the DB trigger as defence in depth)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def _seed_customer_and_account(
    session: AsyncSession, *, customer_id: str, account_id: str
) -> None:
    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name="Avery Nakamura",
            email="avery.nakamura@example.com",
            phone="+1-555-0142",
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
    await session.flush()


@pytest.mark.asyncio
async def test_money_round_trips_exactly_through_delinquency_repository(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_customer_and_account(session, customer_id="cus_000101", account_id="acc_000123")
    session.add(
        DelinquencyRecordOrm(
            account_id="acc_000123",
            customer_id="cus_000101",
            outstanding_balance=Money("8420.10"),
            overdue_amount=Money("0.10"),
            dpd=34,
            bucket="DPD_30_59",
            collection_status="IN_PROGRESS",
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    await session.commit()

    repo = DelinquencyRecordRepository()
    record = await repo.get_by_account(session, "acc_000123", "cus_000101")

    assert record is not None
    assert record.overdue_amount == Money("0.10")
    assert record.overdue_amount.amount == Decimal("0.10")
    assert record.outstanding_balance == Money("8420.10")


@pytest.mark.asyncio
async def test_update_snapshot_increments_record_version(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_customer_and_account(session, customer_id="cus_000102", account_id="acc_000124")
    session.add(
        DelinquencyRecordOrm(
            account_id="acc_000124",
            customer_id="cus_000102",
            outstanding_balance=Money("1000.00"),
            overdue_amount=Money("100.00"),
            dpd=10,
            bucket="DPD_1_29",
            collection_status="NEW",
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    await session.commit()

    repo = DelinquencyRecordRepository()
    later = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    updated = await repo.update_snapshot(
        session,
        account_id="acc_000124",
        customer_id="cus_000102",
        expected_version=1,
        outstanding_balance=Money("950.00"),
        overdue_amount=Money("50.00"),
        dpd=15,
        bucket="DPD_1_29",
        collection_status="IN_PROGRESS",
        as_of=later,
        updated_at=later,
    )
    await session.commit()

    assert updated is True
    record = await repo.get_by_account(session, "acc_000124", "cus_000102")
    assert record is not None
    assert record.record_version == 2
    assert record.overdue_amount == Money("50.00")


@pytest.mark.asyncio
async def test_update_snapshot_with_stale_version_is_a_no_op_conflict(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_customer_and_account(session, customer_id="cus_000103", account_id="acc_000125")
    session.add(
        DelinquencyRecordOrm(
            account_id="acc_000125",
            customer_id="cus_000103",
            outstanding_balance=Money("1000.00"),
            overdue_amount=Money("100.00"),
            dpd=10,
            bucket="DPD_1_29",
            collection_status="NEW",
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    await session.commit()

    repo = DelinquencyRecordRepository()
    updated = await repo.update_snapshot(
        session,
        account_id="acc_000125",
        customer_id="cus_000103",
        expected_version=99,  # stale/wrong expected version
        outstanding_balance=Money("1.00"),
        overdue_amount=Money("1.00"),
        dpd=1,
        bucket="CURRENT",
        collection_status="NEW",
        as_of=_NOW,
        updated_at=_NOW,
    )
    await session.commit()

    assert updated is False
    record = await repo.get_by_account(session, "acc_000125", "cus_000103")
    assert record is not None
    assert record.record_version == 1
    assert record.overdue_amount == Money("100.00")


@pytest.mark.asyncio
async def test_db_trigger_enforces_monotonic_version_even_without_app_increment(
    session: AsyncSession, clean_db: None
) -> None:
    """Defence in depth: even a raw UPDATE that forgets to bump
    record_version is forced to OLD + 1 by the BEFORE UPDATE trigger."""
    await _seed_customer_and_account(session, customer_id="cus_000104", account_id="acc_000126")
    session.add(
        DelinquencyRecordOrm(
            account_id="acc_000126",
            customer_id="cus_000104",
            outstanding_balance=Money("1000.00"),
            overdue_amount=Money("100.00"),
            dpd=10,
            bucket="DPD_1_29",
            collection_status="NEW",
            as_of=_NOW,
            record_version=5,
            updated_at=_NOW,
        )
    )
    await session.commit()

    # Raw UPDATE that does NOT set record_version at all.
    await session.execute(
        text("UPDATE delinquency_record SET dpd = 11 WHERE account_id = :account_id"),
        {"account_id": "acc_000126"},
    )
    await session.commit()

    repo = DelinquencyRecordRepository()
    record = await repo.get_by_account(session, "acc_000126", "cus_000104")
    assert record is not None
    assert record.record_version == 6
