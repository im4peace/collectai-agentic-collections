"""E7-S4 AC1-AC5: exceptional (off-menu) arrangement requests, human
APPROVE/REJECT of them, and the resulting arrangement creation, end to end
against a real, migrated Postgres database. Mirrors
`test_e8_s1_arrangement_flow.py`'s chat fixtures and
`test_e7_s2_review_decisions_api.py`'s `_decide` helper.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.llm_provider.base import ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_810101"
_ACCOUNT_ID = "acc_810201"
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
async def seeded_account(engine: AsyncEngine, clean_db: None) -> None:
    """`overdue_amount` 770.40, dpd 30 -- standard menu is [3, 6, 12]
    (policy-v1.json); a requested count of 7 is off-menu (TERM exception),
    within the collections_officer authority's types (["TERM",
    "START_DATE"]) and comfortably under its max_overdue_amount (3000.00)."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Priya Vasquez",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+1-555-0166",
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
def exception_client(
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
def customer_headers(exception_client: TestClient) -> dict[str, str]:
    response = exception_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def _script(client: TestClient, responses: list[ProviderResult]) -> None:
    client.app.state.chat_llm_provider = MockProvider(list(responses))


def _intent_response(label: str) -> ProviderResult:
    content = json.dumps(
        {
            "label": label,
            "confidence": 0.9,
            "rationale": "Classified from the customer's message.",
            "vulnerability_detected": False,
            "vulnerability_category": None,
            "vulnerability_rationale": "",
            "special_request": "NONE",
        }
    )
    return ProviderResult(content=content, model_id="mock-model-1", latency_ms=5.0)


def _arrangement_extraction_response(*, installment_count: int | None) -> ProviderResult:
    content = json.dumps(
        {
            "promised_amount": None,
            "promised_date": None,
            "payment_option": None,
            "installment_count": installment_count,
        }
    )
    return ProviderResult(content=content, model_id="mock-model-1", latency_ms=5.0)


def _create_conversation(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/chat/conversations", json={"account_id": _ACCOUNT_ID}, headers=headers
    )
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["conversation"]["conversation_id"]
    return conversation_id


def _send(
    client: TestClient, conversation_id: str, headers: dict[str, str], content: str
) -> object:
    return client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )


def _decide(
    client: TestClient, case_id: str, body: dict[str, object], *, idempotency_key: str
) -> object:
    headers = dict(_OFFICER_HEADERS)
    headers["Idempotency-Key"] = idempotency_key
    return client.post(f"/api/escalations/{case_id}/decisions", json=body, headers=headers)


async def _request_exceptional_arrangement(
    exception_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> tuple[str, EscalationCaseOrm]:
    """Drives the real chat flow to open an EXCEPTIONAL_ARRANGEMENT case for
    a 7-installment request (off the [3, 6, 12] standard menu). Returns
    `(conversation_id, case)`."""
    conversation_id = _create_conversation(exception_client, customer_headers)
    _script(
        exception_client,
        [_intent_response("PAYMENT_PLAN"), _arrangement_extraction_response(installment_count=7)],
    )
    result = _send(exception_client, conversation_id, customer_headers, "Can I do 7 payments?")
    assert result.status_code == 200, result.text

    cases = (await session.execute(select(EscalationCaseOrm))).scalars().all()
    exceptional = [c for c in cases if c.reason == "EXCEPTIONAL_ARRANGEMENT"]
    assert len(exceptional) == 1
    return conversation_id, exceptional[0]


# AC1 -------------------------------------------------------------------


async def test_off_menu_request_opens_an_open_exception_review_case_with_requested_terms(
    exception_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id, case = await _request_exceptional_arrangement(
        exception_client, customer_headers, session
    )
    assert case.status == "OPEN"
    assert case.queue == "COLLECTIONS_EXCEPTION_REVIEW"
    assert case.reviewer_role == "COLLECTIONS_OFFICER"
    assert case.requested_terms is not None
    assert case.requested_terms["installment_count"] == 7
    assert case.exception_types == ["TERM"]
    assert case.conversation_id == conversation_id


# AC2 -------------------------------------------------------------------


async def test_customer_message_has_no_approval_language(
    exception_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(exception_client, customer_headers)
    _script(
        exception_client,
        [_intent_response("PAYMENT_PLAN"), _arrangement_extraction_response(installment_count=7)],
    )
    result = _send(exception_client, conversation_id, customer_headers, "Can I do 7 payments?")
    assert result.status_code == 200, result.text
    content = result.json()["assistant_message"]["content"].lower()

    assert "review" in content and "specialist" in content
    for forbidden in ("approved", "we will grant", "you're approved", "granted", "confirmed"):
        assert forbidden not in content, f"{forbidden!r} found in: {content!r}"


# AC3 -------------------------------------------------------------------


async def test_exceptional_terms_never_appear_in_the_standard_menu(
    exception_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(exception_client, customer_headers)
    _script(
        exception_client,
        [
            _intent_response("PAYMENT_PLAN"),
            _arrangement_extraction_response(installment_count=None),
        ],
    )
    result = _send(exception_client, conversation_id, customer_headers, "I want a payment plan")
    assert result.status_code == 200, result.text
    content = result.json()["assistant_message"]["content"]
    # Only the real, policy-standard counts (3, 6, 12) ever appear as an
    # offered option -- "7" (the exceptional count used elsewhere in this
    # file) is never fabricated into the menu.
    assert "7 payments" not in content


# AC4 -------------------------------------------------------------------


async def test_approve_requires_a_reason(
    exception_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    _, case = await _request_exceptional_arrangement(exception_client, customer_headers, session)
    response = _decide(
        exception_client, case.case_id, {"action": "APPROVE", "expected_version": 1},
        idempotency_key="ac4-a",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


async def test_reject_requires_a_reason(
    exception_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    _, case = await _request_exceptional_arrangement(exception_client, customer_headers, session)
    response = _decide(
        exception_client, case.case_id, {"action": "REJECT", "expected_version": 1},
        idempotency_key="ac4-b",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


async def test_approve_is_blocked_outside_the_exception_authority_amount_threshold(
    session: AsyncSession, exception_client: TestClient, customer_headers: dict[str, str]
) -> None:
    """AC4: "thresholds and maximum overdue amount" -- an account above
    policy-v1's 3000.00 max_overdue_amount cannot be approved even for an
    authorized exception *type*."""
    await session.execute(
        text("UPDATE delinquency_record SET overdue_amount = '5000.00' WHERE account_id = :a"),
        {"a": _ACCOUNT_ID},
    )
    await session.commit()
    _, case = await _request_exceptional_arrangement(exception_client, customer_headers, session)

    response = _decide(
        exception_client,
        case.case_id,
        {"action": "APPROVE", "expected_version": 1, "reason": "Within standard authority."},
        idempotency_key="ac4-c",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "NOT_PERMITTED_BY_POLICY"


# AC5 -------------------------------------------------------------------


async def test_approve_creates_the_arrangement_via_the_domain_service(
    exception_client: TestClient,
    customer_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    _, case = await _request_exceptional_arrangement(exception_client, customer_headers, session)

    response = _decide(
        exception_client,
        case.case_id,
        {"action": "APPROVE", "expected_version": 1, "reason": "Within standard authority."},
        idempotency_key="ac5-a",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["arrangement"] is not None
    assert body["arrangement"]["option"]["installment_count"] == 7
    assert body["arrangement"]["created_via"] == "EXCEPTION_APPROVAL"
    assert body["arrangement"]["exception_case_id"] == case.case_id

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "ACTIVE"
    assert rows[0].installment_count == 7
    assert rows[0].created_via == "EXCEPTION_APPROVAL"
    assert rows[0].exception_case_id == case.case_id


async def test_reject_creates_no_arrangement_and_informs_the_customer(
    exception_client: TestClient,
    customer_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    conversation_id, case = await _request_exceptional_arrangement(
        exception_client, customer_headers, session
    )

    response = _decide(
        exception_client,
        case.case_id,
        {"action": "REJECT", "expected_version": 1, "reason": "Outside standard terms."},
        idempotency_key="ac5-b",
    )
    assert response.status_code == 201, response.text
    assert response.json()["arrangement"] is None

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert rows == []

    messages = (
        (
            await session.execute(
                select(ChatMessageOrm).where(ChatMessageOrm.conversation_id == conversation_id)
            )
        )
        .scalars()
        .all()
    )
    informed = [m for m in messages if "not able to approve" in m.content]
    assert len(informed) == 1
