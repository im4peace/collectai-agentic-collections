"""PromiseToPay transition-guard trigger (data-models.md section 4.3):
rejects any UPDATE whose OLD.status is not PENDING and whose NEW.status
differs. Defence in depth ahead of any domain service (none exists yet)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def _seed_ptp(session: AsyncSession, *, status: str) -> None:
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
            customer_id="cus_000301",
            display_name="Synthetic Customer",
            email="synthetic.customer@example.com",
            phone="+1-555-0177",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id="acc_000401",
            customer_id="cus_000301",
            account_type="CARD",
            product_name="Everyday Card",
            currency="USD",
            opened_on=date(2025, 1, 1),
            product_attributes={"credit_limit": "2000.00", "minimum_payment_due": "50.00"},
            created_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        PromiseToPayOrm(
            ptp_id="ptp_000501",
            account_id="acc_000401",
            customer_id="cus_000301",
            promised_amount=Money("250.00"),
            promised_date=date(2026, 10, 15),
            status=status,
            cumulative_paid=Money("0.00"),
            source="CUSTOMER_CHAT",
            created_by_persona="CUSTOMER",
            created_at=_NOW,
            updated_at=_NOW,
            kept_at=_NOW if status == "KEPT" else None,
            policy_version="policy-v1",
            version=1,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_pending_ptp_can_transition_to_kept(session: AsyncSession, clean_db: None) -> None:
    await _seed_ptp(session, status="PENDING")

    await session.execute(
        text(
            "UPDATE promise_to_pay SET status = 'KEPT', kept_at = :now WHERE ptp_id = 'ptp_000501'"
        ),
        {"now": _NOW},
    )
    await session.commit()  # must not raise

    result = await session.execute(
        text("SELECT status FROM promise_to_pay WHERE ptp_id = 'ptp_000501'")
    )
    assert result.scalar_one() == "KEPT"


@pytest.mark.asyncio
async def test_terminal_ptp_cannot_transition_again(session: AsyncSession, clean_db: None) -> None:
    await _seed_ptp(session, status="KEPT")

    with pytest.raises(DBAPIError):
        await session.execute(
            text("UPDATE promise_to_pay SET status = 'CANCELLED' WHERE ptp_id = 'ptp_000501'")
        )
        await session.commit()
    await session.rollback()
