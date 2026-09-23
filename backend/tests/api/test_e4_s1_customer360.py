"""E4-S1 AC1-AC5: `GET /api/customers/{account_id}/360` end to end against a
real, migrated Postgres database. `api/routers/customer360.py` is already
wired into `api/app.py` (Group E's integration pass), so this suite uses
`conftest.py`'s `api_client` directly rather than mounting a probe router.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    ContactOutcome,
    DisputeCategory,
    DisputeStatus,
    EscalationPriority,
    EscalationReason,
    HardshipStatus,
    InteractionChannel,
    InteractionDirection,
    Persona,
    PtpSource,
    PtpStatus,
    ReviewQueue,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_200301"
_CUSTOMER_ID = "cus_200201"
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-v1', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) "
            "ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"created_at": _NOW},
    )


@pytest_asyncio.fixture
async def seeded_account(session: AsyncSession, clean_db: None) -> None:
    """One delinquent account with one of every block AC1 lists: an
    interaction, a PTP, a hardship case, a dispute and an open escalation
    case, so a single request exercises every response block."""
    await _ensure_policy_rule_set_row(session)
    session.add(
        CustomerOrm(
            customer_id=_CUSTOMER_ID,
            display_name="Priya Nakamura",
            email=f"{_CUSTOMER_ID}@example.com",
            phone="+1-555-0177",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            account_type=AccountType.CARD.value,
            product_name="Everyday Card",
            currency="USD",
            opened_on=_NOW.date(),
            product_attributes={},
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            outstanding_balance=Money("3200.00"),
            overdue_amount=Money("640.00"),
            dpd=45,
            bucket=Bucket.DPD_30_59.value,
            collection_status=CollectionStatus.IN_PROGRESS.value,
            as_of=_NOW,
            record_version=3,
            updated_at=_NOW,
        )
    )
    session.add(
        InteractionOrm(
            interaction_id="int_200501",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            channel=InteractionChannel.SIMULATED_OUTBOUND_CALL.value,
            direction=InteractionDirection.OUTBOUND.value,
            outcome=ContactOutcome.PTP_MADE.value,
            occurred_at=_NOW,
            summary="Customer promised to pay the overdue amount.",
            counts_as_attempt=True,
            conversation_id=None,
        )
    )
    session.add(
        PromiseToPayOrm(
            ptp_id="ptp_200401",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            promised_amount=Money("640.00"),
            promised_date=_NOW.date(),
            status=PtpStatus.PENDING.value,
            cumulative_paid=Money("0.00"),
            interaction_reference="int_200501",
            source=PtpSource.OFFICER_MANUAL.value,
            created_by_persona=Persona.COLLECTIONS_OFFICER.value,
            created_at=_NOW,
            updated_at=_NOW,
            kept_at=None,
            broken_at=None,
            cancelled_at=None,
            cancel_reason=None,
            policy_version="policy-v1",
            version=1,
        )
    )
    session.add(
        HardshipCaseOrm(
            hardship_case_id="hsp_200601",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            conversation_id=None,
            status=HardshipStatus.OPEN.value,
            indicators=[{"indicator_type": "JOB_LOSS", "customer_statement": "I lost my job."}],
            escalation_case_id=None,
            created_at=_NOW,
            decided_at=None,
            updated_at=_NOW,
            version=1,
        )
    )
    session.add(
        DisputeOrm(
            dispute_id="dsp_200701",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            category=DisputeCategory.AMOUNT_INCORRECT.value,
            customer_reason="The overdue amount looks wrong.",
            status=DisputeStatus.OPEN.value,
            outcome=None,
            resolution_reason=None,
            conversation_id=None,
            escalation_case_id=None,
            created_at=_NOW,
            resolved_at=None,
            updated_at=_NOW,
            version=1,
        )
    )
    session.add(
        EscalationCaseOrm(
            case_id="esc_200801",
            customer_id=_CUSTOMER_ID,
            account_id=_ACCOUNT_ID,
            reason=EscalationReason.FINANCIAL_HARDSHIP.value,
            queue=ReviewQueue.HARDSHIP_REVIEW.value,
            reviewer_role="COLLECTIONS_OFFICER",
            priority=EscalationPriority.ELEVATED.value,
            status="OPEN",
            source="AI",
            summary="Customer reports job loss.",
            routing_policy_version="policy-v1",
            routing_flags=[],
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.commit()


def test_get_customer_360_returns_every_ac1_block(
    api_client: TestClient, seeded_account: None
) -> None:
    response = api_client.get(f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    body = response.json()

    assert body["account_id"] == _ACCOUNT_ID
    assert body["profile"]["customer_id"] == _CUSTOMER_ID
    assert body["profile"]["display_name"] == "Priya Nakamura"
    assert body["account"]["outstanding_balance"] == "3200.00"
    assert body["account"]["overdue_amount"] == "640.00"
    assert body["account"]["dpd"] == 45
    assert body["account"]["bucket"] == "DPD_30_59"
    assert [row["interaction_id"] for row in body["interactions"]] == ["int_200501"]
    assert [row["ptp_id"] for row in body["ptp_history"]] == ["ptp_200401"]
    assert len(body["hardship_cases"]) == 1
    assert body["hardship_cases"][0]["indicators"][0]["indicator_type"] == "JOB_LOSS"
    assert [row["dispute_id"] for row in body["disputes"]] == ["dsp_200701"]
    assert body["escalation"]["has_open_case"] is True
    assert [row["case_id"] for row in body["escalation"]["cases"]] == ["esc_200801"]


def test_deterministic_and_ai_blocks_are_separately_labelled(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC2: priority band/factors sit under `source="deterministic"`; any
    recommendation sits under `source="ai"` (always absent here -- E4-S3,
    which generates one, does not exist yet)."""
    response = api_client.get(f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    body = response.json()

    assert body["deterministic"]["source"] == "deterministic"
    assert body["deterministic"]["status"] == "OK"
    assert body["deterministic"]["priority"]["band"] in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }
    assert body["deterministic"]["priority"]["policy_version"] == "policy-v1"
    assert len(body["deterministic"]["priority"]["factors"]) > 0

    assert body["ai"]["source"] == "ai"
    assert body["ai"]["status"] == "NOT_GENERATED"
    assert body["ai"]["recommendation"] is None


def test_unknown_account_id_returns_404(api_client: TestClient, seeded_account: None) -> None:
    """AC3."""
    response = api_client.get("/api/customers/acc_does_not_exist/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 404


def test_customer_persona_is_forbidden(
    api_client: TestClient, seeded_account: None, customer_session_headers: dict[str, str]
) -> None:
    """AC3."""
    response = api_client.get(f"/api/customers/{_ACCOUNT_ID}/360", headers=customer_session_headers)
    assert response.status_code == 403


@pytest.mark.parametrize("persona", [Persona.COLLECTIONS_MANAGER, Persona.COMPLIANCE_RISK])
def test_forbidden_for_every_persona_other_than_collections_officer(
    api_client: TestClient, seeded_account: None, persona: Persona
) -> None:
    """AC4."""
    response = api_client.get(
        f"/api/customers/{_ACCOUNT_ID}/360", headers={"X-Persona": persona.value}
    )
    assert response.status_code == 403


def test_snapshot_block_reports_record_version_and_fresh_status(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC5: the seeded snapshot's `as_of` is the same instant the app's
    `SimulatedClock` reports as "now" (`conftest.py`'s `NOW`), so it must be
    FRESH."""
    response = api_client.get(f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["record_version"] == 3
    assert snapshot["freshness"] == "FRESH"
    assert snapshot["max_age_minutes"] == 60


@pytest.mark.asyncio
async def test_snapshot_older_than_the_policy_threshold_is_stale(
    api_client: TestClient, session: AsyncSession, clean_db: None
) -> None:
    """AC5: a snapshot older than `policy-v1`'s 60-minute
    `max_snapshot_age_minutes` is STALE."""
    await _ensure_policy_rule_set_row(session)
    session.add(
        CustomerOrm(
            customer_id="cus_200202",
            display_name="Older Snapshot",
            email="cus_200202@example.com",
            phone="+1-555-0188",
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id="acc_200302",
            customer_id="cus_200202",
            account_type=AccountType.CARD.value,
            product_name="Everyday Card",
            currency="USD",
            opened_on=_NOW.date(),
            product_attributes={},
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id="acc_200302",
            customer_id="cus_200202",
            outstanding_balance=Money("100.00"),
            overdue_amount=Money("50.00"),
            dpd=5,
            bucket=Bucket.DPD_1_29.value,
            collection_status=CollectionStatus.NEW.value,
            as_of=_NOW - timedelta(minutes=90),
            record_version=1,
            updated_at=_NOW - timedelta(minutes=90),
        )
    )
    await session.commit()

    response = api_client.get("/api/customers/acc_200302/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    assert response.json()["snapshot"]["freshness"] == "STALE"


def test_undisputed_overdue_amount_excludes_the_whole_overdue_dispute(
    api_client: TestClient, seeded_account: None
) -> None:
    """A whole-overdue-amount dispute (`item_id is None`) zeroes
    `undisputed_overdue_amount` (`customer360_mapping.undisputed_overdue_amount`)."""
    response = api_client.get(f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    account_block = response.json()["account"]
    assert account_block["overdue_amount"] == "640.00"
    assert Decimal(account_block["undisputed_overdue_amount"]) == Decimal("0.00")
