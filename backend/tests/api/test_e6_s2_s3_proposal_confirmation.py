"""E6-S2 AC1-AC6, E6-S3 AC1-AC5: chat-driven PTP/PAY_NOW proposal creation
and the explicit confirm/cancel actions, end to end against a real, migrated
Postgres database. Mirrors `test_e6_s1_chat_api.py`'s fixtures and
`test_e6_s6_manual_ptp_api.py`'s seeded-account pattern.
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
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_400201"
_ACCOUNT_ID = "acc_400301"


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
    """One account, `overdue_amount` 500.00, `outstanding_balance` 2000.00,
    delinquency snapshot at `_NOW` (record_version 1) -- fresh relative to
    the app's `SimulatedClock`."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Amara Osei",
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
def proposal_client(
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
def customer_headers(proposal_client: TestClient) -> dict[str, str]:
    response = proposal_client.post(
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


def _extraction_response(
    *,
    promised_amount: str | None = None,
    promised_date: str | None = None,
    payment_option: str | None = None,
) -> ProviderResult:
    content = json.dumps(
        {
            "promised_amount": promised_amount,
            "promised_date": promised_date,
            "payment_option": payment_option,
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


def _confirm(
    client: TestClient,
    *,
    conversation_id: str,
    proposal_id: str,
    terms_hash: str,
    headers: dict[str, str],
    idempotency_key: str = "confirm-key-0001",
) -> object:
    request_headers = dict(headers)
    request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/chat/conversations/{conversation_id}/proposals/{proposal_id}/confirm",
        json={"terms_hash": terms_hash},
        headers=request_headers,
    )


# E6-S2 AC1 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_ptp_offer_creates_no_ptp_until_explicitly_confirmed(
    proposal_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )

    result = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is not None
    assert body["proposal"]["kind"] == "PTP"
    assert body["proposal"]["status"] == "PENDING_CONFIRMATION"
    assert "confirm" in body["assistant_message"]["content"].lower()

    ptp_rows = (await session.execute(select(PromiseToPayOrm))).scalars().all()
    assert len(ptp_rows) == 0


# E6-S2 AC1, AC6 ----------------------------------------------------------


@pytest.mark.asyncio
async def test_confirming_the_offered_proposal_creates_exactly_one_pending_ptp(
    proposal_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    turn = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    ).json()
    proposal = turn["proposal"]

    confirm = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert confirm.status_code == 201, confirm.text
    body = confirm.json()
    assert body["outcome"]["kind"] == "PTP"
    assert body["outcome"]["ptp"]["status"] == "PENDING"
    assert body["outcome"]["ptp"]["promised_amount"] == "200.00"
    assert body["replayed"] is False

    rows = (await session.execute(select(PromiseToPayOrm))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "CUSTOMER_CHAT"
    assert rows[0].created_by_persona == "CUSTOMER"


def test_duplicate_confirm_with_same_idempotency_key_replays_and_creates_one_ptp(
    proposal_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    proposal = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    ).json()["proposal"]

    first = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
        idempotency_key="dup-key",
    )
    second = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
        idempotency_key="dup-key",
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert second.json()["replayed"] is True
    assert first.json()["outcome"]["ptp"]["ptp_id"] == second.json()["outcome"]["ptp"]["ptp_id"]


def test_altered_terms_hash_is_rejected_with_proposal_invalid(
    proposal_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    proposal = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    ).json()["proposal"]

    response = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash="0" * 64,
        headers=customer_headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "PROPOSAL_INVALID"


# E6-S2 AC4 ----------------------------------------------------------------


def test_second_ptp_proposal_conflicts_with_an_existing_pending_ptp(
    proposal_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    proposal = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    ).json()["proposal"]
    confirm = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert confirm.status_code == 201, confirm.text

    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="100.00", promised_date="2026-10-20"),
        ],
    )
    second_turn = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "Actually let me promise 100.00 by 2026-10-20"},
        headers=customer_headers,
    ).json()
    second_proposal = second_turn["proposal"]
    assert second_proposal is not None

    second_confirm = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=second_proposal["proposal_id"],
        terms_hash=second_proposal["terms_hash"],
        headers=customer_headers,
        idempotency_key="second-confirm",
    )
    assert second_confirm.status_code == 409, second_confirm.text
    assert second_confirm.json()["error"]["reason_code"] == "CONFLICTING_ACTIVE_ITEM"


# E6-S2 AC2 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_amount_gets_a_deterministic_rejection_and_no_proposal(
    proposal_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="9999.00", promised_date="2026-10-15"),
        ],
    )
    result = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 9999.00 by 2026-10-15"},
        headers=customer_headers,
    )
    assert result.status_code == 200
    body = result.json()
    assert body["proposal"] is None
    ptp_count = (await session.execute(select(PromiseToPayOrm))).scalars().all()
    assert len(ptp_count) == 0


# E6-S3 AC1, AC2, AC4 -------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_now_confirmation_records_one_simulated_payment_event_and_reduces_balance(
    proposal_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [_intent_response("PAY_NOW"), _extraction_response(payment_option="OVERDUE_AMOUNT")],
    )
    turn = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I want to pay the overdue amount now"},
        headers=customer_headers,
    ).json()
    proposal = turn["proposal"]
    assert proposal is not None
    assert proposal["kind"] == "PAYMENT"
    assert proposal["simulated"] is True
    assert "simulated" in turn["assistant_message"]["content"].lower()

    confirm = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert confirm.status_code == 201, confirm.text
    body = confirm.json()
    assert body["outcome"]["kind"] == "PAYMENT"
    assert body["outcome"]["payment_event"]["simulated"] is True
    assert body["outcome"]["payment_event"]["amount"] == "500.00"
    assert "simulated" in body["assistant_message"]["content"].lower()

    events = (await session.execute(select(PaymentEventOrm))).scalars().all()
    assert len(events) == 1
    assert events[0].simulated is True
    assert events[0].balance_after == Money("1500.00")


@pytest.mark.asyncio
async def test_duplicate_payment_confirmation_does_not_double_count_recovery(
    proposal_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [_intent_response("PAY_NOW"), _extraction_response(payment_option="OVERDUE_AMOUNT")],
    )
    proposal = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "pay the overdue amount"},
        headers=customer_headers,
    ).json()["proposal"]

    for _ in range(2):
        response = _confirm(
            proposal_client,
            conversation_id=conversation_id,
            proposal_id=proposal["proposal_id"],
            terms_hash=proposal["terms_hash"],
            headers=customer_headers,
            idempotency_key="pay-key",
        )
        assert response.status_code in (200, 201)

    events = (await session.execute(select(PaymentEventOrm))).scalars().all()
    assert len(events) == 1


# Cancel -----------------------------------------------------------------


def test_cancelling_a_pending_proposal_creates_no_ptp_and_is_idempotent(
    proposal_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(proposal_client, customer_headers)
    _script(
        proposal_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    proposal = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=customer_headers,
    ).json()["proposal"]

    first = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/proposals/{proposal['proposal_id']}/cancel",
        json={},
        headers=customer_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["proposal"]["status"] == "CANCELLED"

    # Naturally idempotent: cancelling an already-CANCELLED proposal is a 200, not an error.
    second = proposal_client.post(
        f"/api/chat/conversations/{conversation_id}/proposals/{proposal['proposal_id']}/cancel",
        json={},
        headers=customer_headers,
    )
    assert second.status_code == 200, second.text

    confirm_attempt = _confirm(
        proposal_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert confirm_attempt.status_code == 409
    assert confirm_attempt.json()["error"]["reason_code"] == "PROPOSAL_INVALID"


# E6-S2 AC6: freshness UNKNOWN at confirm time --------------------------


@pytest_asyncio.fixture
async def seeded_account_with_unknown_freshness(engine: AsyncEngine, clean_db: None) -> None:
    """Same account shape as `seeded_account`, but `as_of=None` -- freshness
    can never be established (`rules_engine.freshness.check_freshness`
    returns UNKNOWN), exercising the AMBIGUOUS_VALIDATION confirm path."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Amara Osei",
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
                overdue_amount=Money("500.00"),
                dpd=30,
                bucket=Bucket.DPD_1_29.value,
                collection_status=CollectionStatus.IN_PROGRESS.value,
                as_of=None,
                record_version=1,
                updated_at=_NOW,
            )
        )
        await db_session.commit()


@pytest.fixture
def unknown_freshness_client(
    migrated_schema: str, clock: SimulatedClock, seeded_account_with_unknown_freshness: None
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
def unknown_freshness_customer_headers(unknown_freshness_client: TestClient) -> dict[str, str]:
    response = unknown_freshness_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def test_confirm_with_unestablishable_freshness_escalates_and_creates_no_ptp(
    unknown_freshness_client: TestClient, unknown_freshness_customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(
        unknown_freshness_client, unknown_freshness_customer_headers
    )
    _script(
        unknown_freshness_client,
        [
            _intent_response("PROMISE_TO_PAY"),
            _extraction_response(promised_amount="200.00", promised_date="2026-10-15"),
        ],
    )
    proposal = unknown_freshness_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "I promise to pay 200.00 by 2026-10-15"},
        headers=unknown_freshness_customer_headers,
    ).json()["proposal"]
    assert proposal is not None

    response = _confirm(
        unknown_freshness_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=unknown_freshness_customer_headers,
    )
    assert response.status_code == 409, response.text
    body = response.json()["error"]
    assert body["reason_code"] == "AMBIGUOUS_VALIDATION"
    assert body["context"]["escalation_case_id"].startswith("esc_")
