"""E8-S4 AC1-AC5: `POST /api/disputes/{dispute_id}/start-review` and
`POST /api/disputes/{dispute_id}/resolve`, end to end against a real,
migrated Postgres database. Mirrors `test_e7_s2_review_decisions_api.py`'s
fixtures and `_seed_case` helper.
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
from collectai.domain_services._ptp_helpers import has_open_dispute
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_840101"
_ACCOUNT_ID = "acc_840201"
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


async def _seed_dispute(
    session: AsyncSession, *, dispute_id: str, status: str = "UNDER_REVIEW", version: int = 1
) -> None:
    session.add(
        DisputeOrm(
            dispute_id=dispute_id,
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            category="AMOUNT_INCORRECT",
            customer_reason="The amount is wrong.",
            status=status,
            outcome=None,
            resolution_reason=None,
            conversation_id=None,
            escalation_case_id=None,
            created_at=_NOW,
            resolved_at=None,
            updated_at=_NOW,
            version=version,
        )
    )
    await session.commit()


@pytest_asyncio.fixture
async def seeded_account(engine: AsyncEngine, clean_db: None) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Tariq Nasser",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+1-555-0199",
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
                overdue_amount=Money("770.40"),
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
def dispute_review_client(
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
def customer_headers(dispute_review_client: TestClient) -> dict[str, str]:
    response = dispute_review_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def _start_review(
    client: TestClient,
    dispute_id: str,
    *,
    idempotency_key: str,
    expected_version: int = 1,
    headers: dict[str, str] | None = None,
) -> object:
    request_headers = dict(headers or _OFFICER_HEADERS)
    request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/disputes/{dispute_id}/start-review",
        json={"expected_version": expected_version},
        headers=request_headers,
    )


def _resolve(
    client: TestClient,
    dispute_id: str,
    body: dict[str, object],
    *,
    idempotency_key: str,
    headers: dict[str, str] | None = None,
) -> object:
    request_headers = dict(headers or _OFFICER_HEADERS)
    request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/disputes/{dispute_id}/resolve", json=body, headers=request_headers
    )


# AC1 -------------------------------------------------------------------


async def test_resolve_requires_an_outcome(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac1_a")
    response = _resolve(
        dispute_review_client,
        "dsp_ac1_a",
        {"reason": "Reviewed.", "expected_version": 1},
        idempotency_key="ac1-a",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "OUTCOME_REQUIRED"


async def test_resolve_requires_a_reason(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac1_b")
    response = _resolve(
        dispute_review_client,
        "dsp_ac1_b",
        {"outcome": "UPHELD", "expected_version": 1},
        idempotency_key="ac1-b",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


# AC2 -------------------------------------------------------------------


async def test_start_review_moves_open_to_under_review_and_is_audited(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac2_a", status="OPEN")
    response = _start_review(dispute_review_client, "dsp_ac2_a", idempotency_key="ac2-a")
    assert response.status_code == 201, response.text
    assert response.json()["dispute"]["status"] == "UNDER_REVIEW"

    events = (
        (
            await session.execute(
                select(AuditEventOrm).where(
                    AuditEventOrm.event_type == "DISPUTE_UNDER_REVIEW",
                    AuditEventOrm.resource_id == "dsp_ac2_a",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].actor_persona == "COLLECTIONS_OFFICER"


async def test_start_review_on_a_non_open_dispute_is_refused(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac2_b", status="UNDER_REVIEW")
    response = _start_review(dispute_review_client, "dsp_ac2_b", idempotency_key="ac2-b")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "INVALID_STATE_TRANSITION"


async def test_resolve_moves_under_review_to_resolved_and_is_audited(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac2_c", status="UNDER_REVIEW")
    response = _resolve(
        dispute_review_client,
        "dsp_ac2_c",
        {"outcome": "UPHELD", "reason": "Confirmed billing error.", "expected_version": 1},
        idempotency_key="ac2-c",
    )
    assert response.status_code == 201, response.text
    body = response.json()["dispute"]
    assert body["status"] == "RESOLVED"
    assert body["outcome"] == "UPHELD"
    assert body["resolution_reason"] == "Confirmed billing error."
    assert body["resolved_at"] is not None

    events = (
        (
            await session.execute(
                select(AuditEventOrm).where(
                    AuditEventOrm.event_type == "DISPUTE_RESOLVED",
                    AuditEventOrm.resource_id == "dsp_ac2_c",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].actor_persona == "COLLECTIONS_OFFICER"


async def test_resolve_on_an_open_dispute_cannot_skip_under_review(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac2_d", status="OPEN")
    response = _resolve(
        dispute_review_client,
        "dsp_ac2_d",
        {"outcome": "UPHELD", "reason": "Confirmed.", "expected_version": 1},
        idempotency_key="ac2-d",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "INVALID_STATE_TRANSITION"


# AC3 -------------------------------------------------------------------


async def test_suppression_lifts_only_once_resolved(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac3_a", status="OPEN")
    assert await has_open_dispute(session, account_id=_ACCOUNT_ID, item_id=None) is True

    started = _start_review(dispute_review_client, "dsp_ac3_a", idempotency_key="ac3-start")
    assert started.status_code == 201, started.text
    assert await has_open_dispute(session, account_id=_ACCOUNT_ID, item_id=None) is True

    resolved = _resolve(
        dispute_review_client,
        "dsp_ac3_a",
        {"outcome": "WITHDRAWN", "reason": "Customer withdrew the dispute.", "expected_version": 2},
        idempotency_key="ac3-resolve",
    )
    assert resolved.status_code == 201, resolved.text
    assert await has_open_dispute(session, account_id=_ACCOUNT_ID, item_id=None) is False


# AC4 -------------------------------------------------------------------


async def test_only_officer_can_resolve_a_dispute(
    dispute_review_client: TestClient, session: AsyncSession, customer_headers: dict[str, str]
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac4_a", status="UNDER_REVIEW")
    body = {"outcome": "UPHELD", "reason": "Reviewed.", "expected_version": 1}

    for label, headers in (
        ("compliance", _COMPLIANCE_HEADERS),
        ("manager", _MANAGER_HEADERS),
        ("customer", customer_headers),
    ):
        response = _resolve(
            dispute_review_client,
            "dsp_ac4_a",
            body,
            idempotency_key=f"ac4-{label}",
            headers=headers,
        )
        assert response.status_code == 403, f"{label}: {response.text}"


# AC5 -------------------------------------------------------------------


async def test_resolve_idempotency_key_replay_does_not_repeat_the_transition(
    dispute_review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, dispute_id="dsp_ac5_a", status="UNDER_REVIEW")
    body = {"outcome": "REJECTED", "reason": "No billing error found.", "expected_version": 1}

    first = _resolve(dispute_review_client, "dsp_ac5_a", body, idempotency_key="ac5-a")
    assert first.status_code == 201, first.text

    second = _resolve(dispute_review_client, "dsp_ac5_a", body, idempotency_key="ac5-a")
    assert second.status_code == 200, second.text
    assert second.json()["replayed"] is True
    assert second.json()["dispute"]["version"] == first.json()["dispute"]["version"]

    dispute = await session.get(DisputeOrm, "dsp_ac5_a")
    assert dispute is not None
    assert dispute.version == 2  # not bumped a second time by the replay

    events = (
        (
            await session.execute(
                select(AuditEventOrm).where(
                    AuditEventOrm.event_type == "DISPUTE_RESOLVED",
                    AuditEventOrm.resource_id == "dsp_ac5_a",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
