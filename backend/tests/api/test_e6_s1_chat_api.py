"""E6-S1 AC1, AC4-AC7 end to end against a real, migrated Postgres database.
AC2/AC3 (schema validation) and the pure AC4 safety-precedence dispatch have
their own focused coverage under `tests/ai_guardrails/test_e6_s1_*`; this
file exercises the same behavior wired through the real HTTP surface,
persistence and audit trail.

`api/routers/chat.py` is deliberately not wired into `api.app.create_app`
yet (a later integration pass does that once every Group E/F sibling story
lands, matching this codebase's own established convention -- see that
router's module docstring). This file therefore builds its own app the same
way `tests/api/conftest.py`'s `api_client` fixture does, then layers
`chat.router` on top and sets `app.state.settings` / `app.state.
chat_llm_provider` directly -- both are documented, intentional test seams
(see `chat.py`'s `get_settings`/`get_llm_provider` docstrings).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.api.routers import chat as chat_router_module
from collectai.application._chat_escalation_reporting import ESCALATION_REQUIRED_EVENT_TYPE
from collectai.audit import queries
from collectai.config.settings import Settings
from collectai.llm_provider.base import ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.chat_turn import ChatTurnOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_SEEDED_ACCOUNT_ID = "acc_000101"
_SECOND_CUSTOMER_ID = "cus_000102"
_SECOND_ACCOUNT_ID = "acc_000102"


def _settings(*, database_url: str, chat_rate_limit_per_minute: int = 20) -> Settings:
    return Settings(
        llm_mode=LlmMode.MOCK,
        anthropic_model=None,
        anthropic_api_key=None,
        tool_call_cap_per_turn=5,
        ai_retry_bound=1,
        max_clarification_turns=2,
        chat_rate_limit_per_minute=chat_rate_limit_per_minute,
        api_rate_limit_per_minute=300,
        provider_timeout_seconds=20,
        proposal_ttl_minutes=30,
        demo_controls_enabled=False,
        database_url=database_url,
    )


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    """E7-S1: `escalation_case.routing_policy_version` carries a real FK to
    `policy_rule_set(policy_version)` (migration 0005) -- any test that can
    trigger escalation-case creation (REQUEST_HUMAN, UNRESOLVED_UNKNOWN) now
    needs a matching row to exist, mirroring the same helper
    `test_e6_s6_manual_ptp_api.py` already uses for `promise_to_pay
    .policy_version`'s identical FK."""
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
async def policy_rule_set_row(engine: AsyncEngine, clean_db: None) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        await db_session.commit()


@pytest.fixture
def chat_client(
    migrated_schema: str, clock: SimulatedClock, clean_db: None, policy_rule_set_row: None
) -> Iterator[TestClient]:
    settings = _settings(database_url=migrated_schema)
    app = create_app(settings, clock=clock)
    app.state.settings = settings
    app.include_router(chat_router_module.router)
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def second_customer_id(engine: AsyncEngine, clean_db: None) -> str:
    """A second seeded customer/account, for AC7's cross-customer checks --
    mirrors `conftest.py`'s own `seeded_customer_id` fixture exactly, for a
    different customer."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        db_session.add(
            CustomerOrm(
                customer_id=_SECOND_CUSTOMER_ID,
                display_name="Amara Osei",
                email="amara.osei@example.com",
                phone="+1-555-0102",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        await db_session.flush()
        db_session.add(
            AccountOrm(
                account_id=_SECOND_ACCOUNT_ID,
                customer_id=_SECOND_CUSTOMER_ID,
                account_type="CARD",
                product_name="Everyday Card",
                currency="AED",
                opened_on=_NOW.date(),
                product_attributes={},
                created_at=_NOW,
            )
        )
        await db_session.flush()
        db_session.add(
            DelinquencyRecordOrm(
                account_id=_SECOND_ACCOUNT_ID,
                customer_id=_SECOND_CUSTOMER_ID,
                outstanding_balance=Money("0.00"),
                overdue_amount=Money("0.00"),
                dpd=0,
                bucket=Bucket.CURRENT.value,
                collection_status=CollectionStatus.NEW.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            )
        )
        await db_session.commit()
    return _SECOND_CUSTOMER_ID


@pytest.fixture
def second_customer_headers(chat_client: TestClient, second_customer_id: str) -> dict[str, str]:
    response = chat_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": second_customer_id}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def _script(client: TestClient, responses: list[ProviderResult]) -> None:
    client.app.state.chat_llm_provider = MockProvider(list(responses))


def _intent_response(
    label: str,
    *,
    confidence: float = 0.9,
    vulnerability_detected: bool = False,
    vulnerability_category: str | None = None,
    special_request: str = "NONE",
) -> ProviderResult:
    content = json.dumps(
        {
            "label": label,
            "confidence": confidence,
            "rationale": "Classified from the customer's message.",
            "vulnerability_detected": vulnerability_detected,
            "vulnerability_category": vulnerability_category,
            "vulnerability_rationale": (
                "Customer mentioned a difficult personal situation."
                if vulnerability_detected
                else ""
            ),
            "special_request": special_request,
        }
    )
    return ProviderResult(
        content=content, model_id="mock-model-1", latency_ms=5.0, input_tokens=12, output_tokens=40
    )


def _extraction_response(
    *,
    promised_amount: str | None = None,
    promised_date: str | None = None,
    payment_option: str | None = None,
) -> ProviderResult:
    """E6-S2/E6-S3: the second scripted response a PAY_NOW/PROMISE_TO_PAY
    message now consumes (`ai_orchestration.schemas.proposal_extraction
    .ProposalExtractionResult`), on top of the intent-classification
    response every message already scripted."""
    content = json.dumps(
        {
            "promised_amount": promised_amount,
            "promised_date": promised_date,
            "payment_option": payment_option,
        }
    )
    return ProviderResult(
        content=content, model_id="mock-model-1", latency_ms=5.0, input_tokens=12, output_tokens=20
    )


def _create_conversation(
    client: TestClient, headers: dict[str, str], account_id: str = _SEEDED_ACCOUNT_ID
) -> str:
    response = client.post(
        "/api/chat/conversations", json={"account_id": account_id}, headers=headers
    )
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["conversation"]["conversation_id"]
    return conversation_id


@dataclass(frozen=True, slots=True)
class _MessageResult:
    """`response.json()` is untyped (`Any`) by nature -- these tests parse
    arbitrary JSON envelopes and assert on individual fields, so `body`
    stays `Any` rather than a narrower type that would make every
    `result.body["..."]` access below fail under `mypy --strict`."""

    status_code: int
    headers: Mapping[str, str]
    body: Any


def _send(
    client: TestClient, conversation_id: str, headers: dict[str, str], content: str
) -> _MessageResult:
    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )
    return _MessageResult(
        status_code=response.status_code, headers=response.headers, body=response.json()
    )


# AC1 -----------------------------------------------------------------------


def test_greeting_discloses_ai_assistant_and_offers_human(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    response = chat_client.post(
        "/api/chat/conversations",
        json={"account_id": _SEEDED_ACCOUNT_ID},
        headers=customer_session_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["talk_to_human_available"] is True
    greeting = body["greeting"]
    assert "AI" in greeting["content"]
    assert "AI_DISCLOSURE" in greeting["labels"]
    assert greeting["role"] == "ASSISTANT"
    assert greeting["content_source"] == "TEMPLATE"


def test_message_response_always_offers_talk_to_human(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("PAY_NOW"), _extraction_response()])

    result = _send(chat_client, conversation_id, customer_session_headers, "I want to pay today")

    assert result.status_code == 200, result.body
    assert result.body["talk_to_human_available"] is True


# AC4 -------------------------------------------------------------------


def test_transactional_intent_alone_gets_a_templated_acknowledgement(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("PROMISE_TO_PAY"), _extraction_response()])

    result = _send(
        chat_client, conversation_id, customer_session_headers, "I promise to pay next Friday"
    )

    assert result.status_code == 200
    body = result.body
    # No amount/date extracted -> the deterministic clarification message
    # (E6-S2 AC1: no proposal from the initial statement alone).
    assert "promise to pay" in body["assistant_message"]["content"].lower()
    assert body["proposal"] is None
    assert body["escalation_reported"] is False
    assert body["safe_state"] == "NONE"


def test_transactional_intent_with_vulnerability_detected_is_overridden_by_sensitivity(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    """AC4's explicit dual-signal case."""
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(
        chat_client,
        [
            _intent_response(
                "PROMISE_TO_PAY",
                vulnerability_detected=True,
                vulnerability_category="SERIOUS_ILLNESS_OR_DISABILITY",
            )
        ],
    )

    result = _send(
        chat_client,
        conversation_id,
        customer_session_headers,
        "I can pay next week but I'm in hospital right now",
    )

    assert result.status_code == 200
    body = result.body
    assert body["intent"]["vulnerability_detected"] is True
    assert "promise to pay" not in body["assistant_message"]["content"].lower()
    assert "specialist" in body["assistant_message"]["content"].lower()
    assert body["escalation_reported"] is False


def test_dispute_intent_pauses_automated_treatment_without_an_escalation_report(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("DISPUTE")])

    result = _send(chat_client, conversation_id, customer_session_headers, "This charge isn't mine")

    assert result.status_code == 200
    body = result.body
    assert body["escalation_reported"] is False
    assert body["escalation_reason"] is None
    assert "specialist" in body["assistant_message"]["content"].lower()


# AC5 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_consecutive_unknowns_clarify_twice_then_escalate(
    chat_client: TestClient, customer_session_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("UNKNOWN") for _ in range(3)])

    first = _send(chat_client, conversation_id, customer_session_headers, "hmm not sure")
    second = _send(chat_client, conversation_id, customer_session_headers, "still not sure")
    third = _send(chat_client, conversation_id, customer_session_headers, "sorry, still unclear")

    assert first.status_code == second.status_code == third.status_code == 200
    assert first.body["escalation_reported"] is False
    assert second.body["escalation_reported"] is False
    assert third.body["escalation_reported"] is True
    assert third.body["escalation_reason"] == "UNRESOLVED_UNKNOWN"

    events = await queries.list_by_correlation_id(session, third.body["correlation_id"])
    escalation_events = [e for e in events if e.event_type == ESCALATION_REQUIRED_EVENT_TYPE]
    assert len(escalation_events) == 1
    assert escalation_events[0].reason_code == "UNRESOLVED_UNKNOWN"

    conversation = await session.get(ConversationOrm, conversation_id)
    assert conversation is not None
    assert conversation.clarification_count == 0
    assert conversation.status == "ACTIVE"


@pytest.mark.asyncio
async def test_request_human_escalates_immediately_and_hands_off_the_conversation(
    chat_client: TestClient, customer_session_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("REQUEST_HUMAN")])

    result = _send(
        chat_client, conversation_id, customer_session_headers, "I want to speak to a person please"
    )

    assert result.status_code == 200
    body = result.body
    assert body["escalation_reported"] is True
    assert body["escalation_reason"] == "REQUEST_HUMAN"

    events = await queries.list_by_correlation_id(session, body["correlation_id"])
    escalation_events = [e for e in events if e.event_type == ESCALATION_REQUIRED_EVENT_TYPE]
    assert len(escalation_events) == 1
    assert escalation_events[0].reason_code == "REQUEST_HUMAN"

    conversation = await session.get(ConversationOrm, conversation_id)
    assert conversation is not None
    assert conversation.status == "HANDED_OFF"

    # No responses left scripted: if the follow-up called the provider at
    # all, MockProvider would raise and this would 500, not 200 -- proving
    # api-contracts.md 3.8's "no provider call" claim for a HANDED_OFF
    # conversation.
    follow_up = _send(chat_client, conversation_id, customer_session_headers, "hello again")
    assert follow_up.status_code == 200, follow_up.body
    assert "specialist" in follow_up.body["assistant_message"]["content"].lower()
    assert follow_up.body["intent"] is None


# AC6 -------------------------------------------------------------------


def test_more_than_the_configured_requests_per_minute_returns_429(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    # FINANCIAL_HARDSHIP (a sensitive intent) rather than PAY_NOW: this test
    # only cares about the rate limiter, not the proposal flow, and a
    # sensitive intent needs exactly one scripted response per message
    # (E6-S2/E6-S3's extraction call never runs for a sensitive intent).
    _script(chat_client, [_intent_response("FINANCIAL_HARDSHIP") for _ in range(20)])

    for _ in range(20):
        result = _send(chat_client, conversation_id, customer_session_headers, "checking in")
        assert result.status_code == 200, result.body

    blocked = _send(chat_client, conversation_id, customer_session_headers, "checking in again")
    assert blocked.status_code == 429
    assert blocked.body["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in blocked.headers


# AC7 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_customer_conversation_read_returns_404_and_is_audited(
    chat_client: TestClient,
    customer_session_headers: dict[str, str],
    second_customer_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)

    response = chat_client.get(
        f"/api/chat/conversations/{conversation_id}", headers=second_customer_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

    correlation_id = response.headers["X-Correlation-Id"]
    events = await queries.list_by_correlation_id(session, correlation_id)
    denial_events = [e for e in events if e.event_type == "CROSS_CUSTOMER_ACCESS_DENIED"]
    assert len(denial_events) == 1
    assert denial_events[0].customer_id == _SECOND_CUSTOMER_ID


@pytest.mark.asyncio
async def test_cross_customer_message_returns_no_data_and_is_audited(
    chat_client: TestClient,
    customer_session_headers: dict[str, str],
    second_customer_headers: dict[str, str],
    session: AsyncSession,
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)

    response = chat_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "what is this other customer's balance?"},
        headers=second_customer_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

    correlation_id = response.headers["X-Correlation-Id"]
    events = await queries.list_by_correlation_id(session, correlation_id)
    denial_events = [e for e in events if e.event_type == "CROSS_CUSTOMER_ACCESS_DENIED"]
    assert len(denial_events) == 1


# Persistence: single-owner state mutation ------------------------------


@pytest.mark.asyncio
async def test_one_message_call_writes_exactly_one_customer_and_assistant_message_and_one_turn(
    chat_client: TestClient, customer_session_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    _script(chat_client, [_intent_response("PAY_NOW"), _extraction_response()])

    result = _send(chat_client, conversation_id, customer_session_headers, "I'd like to pay now")
    assert result.status_code == 200, result.body

    message_count = (
        await session.execute(
            select(func.count())
            .select_from(ChatMessageOrm)
            .where(ChatMessageOrm.conversation_id == conversation_id)
        )
    ).scalar_one()
    turn_count = (
        await session.execute(
            select(func.count())
            .select_from(ChatTurnOrm)
            .where(ChatTurnOrm.conversation_id == conversation_id)
        )
    ).scalar_one()

    # 1 greeting (from conversation creation) + 1 customer + 1 assistant.
    assert message_count == 3
    assert turn_count == 1


# List/detail endpoints ---------------------------------------------------


def test_list_and_get_conversation_endpoints(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)

    listing = chat_client.get("/api/chat/conversations", headers=customer_session_headers)
    assert listing.status_code == 200
    assert any(item["conversation_id"] == conversation_id for item in listing.json()["items"])

    detail = chat_client.get(
        f"/api/chat/conversations/{conversation_id}", headers=customer_session_headers
    )
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["labels"] == ["AI_DISCLOSURE"]


# AC2/AC3 wiring: fail-closed on invalid provider output -----------------


def test_schema_invalid_provider_output_falls_back_to_safe_ai_unavailable_state(
    chat_client: TestClient, customer_session_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(chat_client, customer_session_headers)
    bad = ProviderResult(content="not valid json", model_id="mock-model-1", latency_ms=5.0)
    _script(chat_client, [bad, bad])  # initial attempt + one correction retry

    result = _send(chat_client, conversation_id, customer_session_headers, "I want to pay")

    assert result.status_code == 200, result.body
    body = result.body
    assert body["safe_state"] == "AI_UNAVAILABLE"
    assert body["intent"] is None
    assert body["talk_to_human_available"] is True
