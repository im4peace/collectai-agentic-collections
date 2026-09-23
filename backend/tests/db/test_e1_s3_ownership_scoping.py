"""AC6: every customer-owned record carries an owning customer_id FK, and a
repository query by customer_id returns only that customer's records — even
across two different customers' accounts, items, and interactions."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquentItemOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.delinquent_item_repository import DelinquentItemRepository
from collectai.persistence.repositories.interaction_repository import InteractionRepository
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def _seed_two_customers_with_accounts(session: AsyncSession) -> None:
    for customer_id, account_id in (("cus_000201", "acc_000301"), ("cus_000202", "acc_000302")):
        session.add(
            CustomerOrm(
                customer_id=customer_id,
                display_name="Synthetic Customer",
                email="synthetic.customer@example.com",
                phone="+1-555-0199",
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
                account_type="CARD",
                product_name="Everyday Card",
                currency="AED",
                opened_on=date(2025, 1, 1),
                product_attributes={
                    "credit_limit": "2000.00",
                    "minimum_payment_due": "50.00",
                },
                created_at=_NOW,
            )
        )
        await session.flush()
        session.add(
            DelinquentItemOrm(
                item_id=f"itm_{account_id[-6:]}",
                account_id=account_id,
                customer_id=customer_id,
                kind="FEE_OR_CHARGE",
                label="Late fee",
                amount_outstanding=Money("25.00"),
                due_date=date(2026, 8, 1),
                status="OPEN",
            )
        )
        session.add(
            InteractionOrm(
                interaction_id=f"int_{account_id[-6:]}",
                account_id=account_id,
                customer_id=customer_id,
                channel="SIMULATED_OUTBOUND_CALL",
                direction="OUTBOUND",
                outcome="NO_CONTACT",
                occurred_at=_NOW,
                summary="Simulated outbound call, no answer.",
                counts_as_attempt=True,
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_account_list_by_customer_returns_only_that_customers_accounts(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_two_customers_with_accounts(session)

    repo = AccountRepository()
    rows = await repo.list_by_customer(session, "cus_000201")

    assert [row.account_id for row in rows] == ["acc_000301"]


@pytest.mark.asyncio
async def test_account_get_by_id_for_wrong_customer_returns_none(
    session: AsyncSession, clean_db: None
) -> None:
    """A row that belongs to a different customer is indistinguishable from
    a missing row (data-models.md section 1 ownership rule)."""
    await _seed_two_customers_with_accounts(session)

    repo = AccountRepository()
    row = await repo.get_by_id_for_customer(session, "acc_000301", customer_id="cus_000202")

    assert row is None


@pytest.mark.asyncio
async def test_delinquent_item_list_by_customer_is_scoped(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_two_customers_with_accounts(session)

    repo = DelinquentItemRepository()
    rows = await repo.list_by_customer(session, "cus_000202")

    assert [row.item_id for row in rows] == ["itm_000302"]


@pytest.mark.asyncio
async def test_interaction_list_by_customer_is_scoped(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_two_customers_with_accounts(session)

    repo = InteractionRepository()
    rows = await repo.list_by_customer(session, "cus_000201")

    assert [row.interaction_id for row in rows] == ["int_000301"]
