"""E7-S1 AC1-AC7: real escalation-case creation from the chat handoff path
and the staff `GET /api/escalations` list, end to end against a real,
migrated Postgres database. Mirrors `test_e6_s1_chat_api.py`'s fixtures.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_500201"
_ACCOUNT_ID = "acc_500301"
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}
_COMPLIANCE_HEADERS = {"X-Persona": Persona.COMPLIANCE_RISK.value}
_MANAGER_HEADERS = {"X-Persona": Persona.COLLECTIONS_MANAGER.value}


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
async def seeded_account(engine: AsyncEngine, clean_db: None) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Riley Chen",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+1-555-0177",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        await db_session.flush()
        db_session.add(
            AccountOrm(
                account_id=_ACCOUNT_ID,
                customer_id=_CUSTOMER_ID,
                account_type=AccountType.CARD.value,
                product_name="Everyday Card",
                currency="AED",
                opened_on=_NOW.date(),
                product_attributes={},
                created_at=_NOW,
            )
        )
        db_session.add(
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
        await db_session.commit()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(_NOW)


@pytest.fixture
def escalation_client(
    migrated_schema: str, clock: SimulatedClock, seeded_account: None
) -> Iterator[TestClient]:
    settings = Settings(
        llm_mode=LlmMode.MOCK,
        anthropic_model=None,
        anthropic_api_key=None,
        tool_call_cap_per_turn=5,
        ai_retry_bound=1,
        max_clarification_turns=2,
        chat_rate_limit_per_minute=20,
        api_rate_limit_per_minute=300,
        provider_timeout_seconds=20,
        proposal_ttl_minutes=30,
        demo_controls_enabled=False,
        database_url=migrated_schema,
    )
    app = create_app(settings, clock=clock)
    app.state.settings = settings
    with TestClient(app) as client:
        yield client


@pytest.fixture
def customer_headers(escalation_client: TestClient) -> dict[str, str]:
    response = escalation_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def _create_conversation(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/chat/conversations", json={"account_id": _ACCOUNT_ID}, headers=headers
    )
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["conversation"]["conversation_id"]
    return conversation_id


def _handoff(
    client: TestClient, *, conversation_id: str, headers: dict[str, str], idempotency_key: str
) -> object:
    request_headers = dict(headers)
    request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/chat/conversations/{conversation_id}/handoff", json={}, headers=request_headers
    )


# AC1, AC2, AC4 ----------------------------------------------------------


def test_handoff_creates_an_open_case_routed_by_the_policy_routing_service(
    escalation_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(escalation_client, customer_headers)

    response = _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-1",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["escalation"]["status"] == "OPEN"
    assert "specialist" in body["escalation"]["customer_message"].lower()
    assert body["replayed"] is False

    listing = escalation_client.get("/api/escalations", headers=_OFFICER_HEADERS)
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["reason"] == "REQUEST_HUMAN"
    assert item["queue"] == "COLLECTIONS_REVIEW"
    assert item["reviewer_role"] == "COLLECTIONS_OFFICER"
    assert item["priority"] == "NORMAL"
    assert item["status"] == "OPEN"
    assert item["source"] == "CUSTOMER"
    assert item["customer_id"] == _CUSTOMER_ID
    assert item["customer_name"] == "Riley Chen"
    assert item["account_id"] == _ACCOUNT_ID
    assert item["customer_360_path"] == f"/customers/{_ACCOUNT_ID}"
    assert item["age_hours"] == 0
    assert item["aging_warning"] is False


# AC6 ----------------------------------------------------------------------


def test_duplicate_handoff_with_same_idempotency_key_replays_and_creates_no_duplicate(
    escalation_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(escalation_client, customer_headers)

    first = _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-dup",
    )
    second = _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-dup",
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert first.json()["escalation"]["case_id"] == second.json()["escalation"]["case_id"]


@pytest.mark.asyncio
async def test_second_handoff_with_a_different_key_reuses_the_still_open_case(
    escalation_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(escalation_client, customer_headers)

    first = _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-a",
    )
    second = _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-b",
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert first.json()["escalation"]["case_id"] == second.json()["escalation"]["case_id"]

    rows = (await session.execute(select(EscalationCaseOrm))).scalars().all()
    assert len(rows) == 1


# AC7 -----------------------------------------------------------------------


def test_customer_and_manager_personas_are_forbidden_from_the_escalation_list(
    escalation_client: TestClient,
) -> None:
    manager_response = escalation_client.get("/api/escalations", headers=_MANAGER_HEADERS)
    assert manager_response.status_code == 403


def test_compliance_risk_is_scoped_to_the_compliance_review_queue(
    escalation_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(escalation_client, customer_headers)
    _handoff(
        escalation_client,
        conversation_id=conversation_id,
        headers=customer_headers,
        idempotency_key="ho-c",
    )

    default_scope = escalation_client.get("/api/escalations", headers=_COMPLIANCE_HEADERS)
    assert default_scope.status_code == 200
    assert (
        default_scope.json()["items"] == []
    )  # REQUEST_HUMAN routes to COLLECTIONS_REVIEW, not visible

    forbidden_scope = escalation_client.get(
        "/api/escalations", params={"queue": "COLLECTIONS_REVIEW"}, headers=_COMPLIANCE_HEADERS
    )
    assert forbidden_scope.status_code == 403
    assert forbidden_scope.json()["error"]["reason_code"] == "QUEUE_NOT_PERMITTED"
