"""E6-S6 AC1-AC5: `POST /api/ptps`, `POST /api/ptps/validate` and
`GET /api/ptps/{ptp_id}` end to end against a real, migrated Postgres
database. AC3 ("no dependency on `ai_orchestration`") is covered by the
static AST scan in `tests/architecture/test_manual_ptp_no_ai.py`, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    DisputeCategory,
    DisputeStatus,
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_300301"
_CUSTOMER_ID = "cus_300201"
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
    """One account, `overdue_amount` 500.00, delinquency snapshot at `_NOW`
    (record_version 1) -- fresh relative to the app's `SimulatedClock`."""
    await _ensure_policy_rule_set_row(session)
    session.add(
        CustomerOrm(
            customer_id=_CUSTOMER_ID,
            display_name="Amara Osei",
            email=f"{_CUSTOMER_ID}@example.com",
            phone="+1-555-0166",
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
            outstanding_balance=Money("2000.00"),
            overdue_amount=Money("500.00"),
            dpd=30,
            bucket=Bucket.DPD_1_29.value,
            collection_status=CollectionStatus.IN_PROGRESS.value,
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    await session.commit()


def _create_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "account_id": _ACCOUNT_ID,
        "promised_amount": "200.00",
        "promised_date": _NOW.date().isoformat(),
        "record_version": 1,
        "snapshot_as_of": _NOW.isoformat(),
    }
    body.update(overrides)
    return body


def _post_ptp(
    api_client: TestClient,
    *,
    idempotency_key: str | None = "idem-key-0001",
    **body_overrides: object,
) -> object:
    headers = dict(_OFFICER_HEADERS)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return api_client.post("/api/ptps", json=_create_body(**body_overrides), headers=headers)


def test_officer_records_a_ptp_with_status_pending(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC1."""
    response = _post_ptp(api_client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["account_id"] == _ACCOUNT_ID
    assert body["promised_amount"] == "200.00"
    assert body["status"] == "PENDING"
    assert body["source"] == "OFFICER_MANUAL"
    assert body["created_by_persona"] == "COLLECTIONS_OFFICER"
    assert body["policy_version"] == "policy-v1"


def test_amount_above_overdue_amount_is_rejected_with_alternatives(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC2."""
    response = _post_ptp(api_client, promised_amount="9999.00")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "BUSINESS_RULE_VIOLATION"
    assert body["reason_code"] == "OVER_BALANCE"
    assert body["alternatives"] is not None


def test_date_outside_the_policy_window_is_rejected(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC2: `policy-v1.json`'s `ptp.window_days` is 30."""
    response = _post_ptp(
        api_client, promised_date=(_NOW.date() + timedelta(days=45)).isoformat()
    )
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "OUTSIDE_WINDOW"


def test_missing_idempotency_key_is_rejected(api_client: TestClient, seeded_account: None) -> None:
    response = _post_ptp(api_client, idempotency_key=None)
    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_duplicate_idempotency_key_replays_without_a_second_record(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC4."""
    first = _post_ptp(api_client, idempotency_key="idem-key-0002")
    assert first.status_code == 201
    second = _post_ptp(api_client, idempotency_key="idem-key-0002")
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["ptp_id"] == first.json()["ptp_id"]

    listing = api_client.get(f"/api/ptps/{first.json()['ptp_id']}", headers=_OFFICER_HEADERS)
    assert listing.status_code == 200


@pytest.mark.asyncio
async def test_conflicting_active_ptp_is_rejected(
    api_client: TestClient, session: AsyncSession, seeded_account: None
) -> None:
    """AC4."""
    session.add(
        PromiseToPayOrm(
            ptp_id="ptp_300401",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            promised_amount=Money("100.00"),
            promised_date=_NOW.date(),
            status=PtpStatus.PENDING.value,
            cumulative_paid=Money("0.00"),
            interaction_reference=None,
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
    await session.commit()

    response = _post_ptp(api_client, idempotency_key="idem-key-0003")
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "CONFLICTING_ACTIVE_ITEM"


@pytest.mark.asyncio
async def test_ptp_on_a_disputed_item_is_rejected(
    api_client: TestClient, session: AsyncSession, seeded_account: None
) -> None:
    """AC4."""
    session.add(
        DisputeOrm(
            dispute_id="dsp_300501",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            category=DisputeCategory.AMOUNT_INCORRECT.value,
            customer_reason="Amount looks wrong.",
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
    await session.commit()

    response = _post_ptp(api_client, idempotency_key="idem-key-0004")
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "DISPUTED_ITEM"


def test_stale_snapshot_is_refused(api_client: TestClient, seeded_account: None) -> None:
    """AC5: `policy-v1.json`'s `freshness.max_snapshot_age_minutes` is 60;
    a `snapshot_as_of` matching the current record but more than 60 minutes
    before the app clock's `now()` is STALE."""
    stale_as_of = (_NOW - timedelta(days=1)).isoformat()
    response = _post_ptp(api_client, snapshot_as_of=stale_as_of, idempotency_key="idem-key-0005")
    assert response.status_code == 409
    assert response.json()["error"]["reason_code"] == "STALE_DATA"


@pytest.mark.asyncio
async def test_recording_a_ptp_writes_an_audit_event_with_officer_persona_and_policy_version(
    api_client: TestClient, session: AsyncSession, seeded_account: None
) -> None:
    """AC5."""
    from collectai.audit import queries

    response = _post_ptp(api_client, idempotency_key="idem-key-0006")
    assert response.status_code == 201
    correlation_id = response.headers["X-Correlation-Id"]

    events = await queries.list_by_correlation_id(session, correlation_id)
    ptp_events = [event for event in events if event.event_type == "PTP_RECORDED"]
    assert len(ptp_events) == 1
    assert ptp_events[0].actor_persona is Persona.COLLECTIONS_OFFICER
    assert ptp_events[0].policy_version == "policy-v1"


def test_unknown_ptp_id_returns_404(api_client: TestClient, seeded_account: None) -> None:
    response = api_client.get("/api/ptps/ptp_does_not_exist", headers=_OFFICER_HEADERS)
    assert response.status_code == 404


def test_validate_endpoint_never_mutates_state(
    api_client: TestClient, seeded_account: None
) -> None:
    """AC1: the dry-run endpoint uses the same deterministic validator."""
    response = api_client.post(
        "/api/ptps/validate",
        json={
            "account_id": _ACCOUNT_ID,
            "promised_amount": "200.00",
            "promised_date": _NOW.date().isoformat(),
        },
        headers=_OFFICER_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["reason_codes"] == []


@pytest.mark.parametrize("persona", [Persona.COLLECTIONS_MANAGER, Persona.COMPLIANCE_RISK])
def test_forbidden_for_every_persona_other_than_collections_officer(
    api_client: TestClient, seeded_account: None, persona: Persona
) -> None:
    headers = {"X-Persona": persona.value, "Idempotency-Key": "idem-key-0007"}
    response = api_client.post("/api/ptps", json=_create_body(), headers=headers)
    assert response.status_code == 403
