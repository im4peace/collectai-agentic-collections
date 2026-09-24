"""E8-S1 AC1-AC9: chat-driven payment-arrangement proposal creation and its
explicit confirm action, end to end against a real, migrated Postgres
database. Mirrors `test_e6_s2_s3_proposal_confirmation.py`'s fixtures and
helper shape exactly (same `seeded_account`/`proposal_client`/`_script`/
`_create_conversation`/`_confirm` pattern), with `policy-v1.json`'s
`arrangement.installment_counts` = [3, 6, 12] as the standard menu.
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
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import Settings
from collectai.llm_provider.base import ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_800101"
_ACCOUNT_ID = "acc_800201"


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
    """`overdue_amount` 770.40, dpd 30: eligible for all three of policy-v1's
    standard installment counts (3, 6, 12), each installment above the
    25.00 minimum -- same fixture shape already proven in
    `test_e7_s2_review_decisions_api.py`/`test_e5_s4_tool_backend.py`."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Farah Haddad",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+1-555-0188",
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
def arrangement_client(
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
def customer_headers(arrangement_client: TestClient) -> dict[str, str]:
    response = arrangement_client.post(
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


def _extraction_response(*, installment_count: int | None = None) -> ProviderResult:
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


# AC1 ---------------------------------------------------------------------


async def test_menu_lists_only_service_returned_options_with_matching_decimal_amounts(
    arrangement_client: TestClient, customer_headers: dict[str, str]
) -> None:
    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=None)],
    )

    result = _send(arrangement_client, conversation_id, customer_headers, "I want a payment plan")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is None
    content = body["assistant_message"]["content"]
    # Every count policy-v1 offers (3, 6, 12) appears, with the exact
    # service Decimal amount for this account (770.40 / 3 => 256.80).
    assert "3 payments of 256.80" in content
    assert "6 payments" in content
    assert "12 payments" in content


async def test_offering_a_standard_count_creates_no_arrangement_until_confirmed(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=3)],
    )

    result = _send(
        arrangement_client, conversation_id, customer_headers, "3 payments please"
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is not None
    assert body["proposal"]["kind"] == "ARRANGEMENT"
    assert body["proposal"]["status"] == "PENDING_CONFIRMATION"
    assert body["proposal"]["terms"]["installment_count"] == 3
    assert body["proposal"]["terms"]["installment_amount"] == "256.80"

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert rows == []


# AC3, AC5, AC6 -------------------------------------------------------------


async def test_confirming_creates_one_active_arrangement_with_audit_and_is_idempotent(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=3)],
    )
    offer = _send(arrangement_client, conversation_id, customer_headers, "3 payments please")
    proposal = offer.json()["proposal"]

    first = _confirm(
        arrangement_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert first.status_code == 201, first.text
    outcome = first.json()["outcome"]
    assert outcome["kind"] == "ARRANGEMENT"
    assert outcome["arrangement"]["status"] == "ACTIVE"
    assert outcome["arrangement"]["option"]["installment_count"] == 3
    assert outcome["arrangement"]["policy_version"] == "policy-v1"

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "ACTIVE"
    assert rows[0].created_via == "CUSTOMER_CONFIRMATION"

    # AC6: replaying the same idempotency key returns the same arrangement,
    # never a second row.
    second = _confirm(
        arrangement_client,
        conversation_id=conversation_id,
        proposal_id=proposal["proposal_id"],
        terms_hash=proposal["terms_hash"],
        headers=customer_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["outcome"]["arrangement"]["arrangement_id"] == (
        first.json()["outcome"]["arrangement"]["arrangement_id"]
    )
    rows_after_replay = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert len(rows_after_replay) == 1


# AC2 -------------------------------------------------------------------


async def test_no_eligible_options_tells_the_customer_and_offers_a_human(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    # Below policy-v1's min_overdue_amount (100.00): NOT_ELIGIBLE, no
    # conflicting item, so the generic (non-AMEND/CANCEL) message applies.
    await session.execute(
        text("UPDATE delinquency_record SET overdue_amount = '50.00' WHERE account_id = :a"),
        {"a": _ACCOUNT_ID},
    )
    await session.commit()

    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=None)],
    )

    result = _send(arrangement_client, conversation_id, customer_headers, "I want a payment plan")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is None
    assert "can't offer a payment plan" in body["assistant_message"]["content"]
    assert "human" in body["assistant_message"]["content"].lower()


# AC8 -------------------------------------------------------------------


async def test_conflicting_active_ptp_blocks_the_plan_and_offers_amend_cancel_or_officer(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    session.add(
        PromiseToPayOrm(
            ptp_id="ptp_conflict001",
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            promised_amount=Money("200.00"),
            promised_date=_NOW.date(),
            status="PENDING",
            cumulative_paid=Money("0"),
            interaction_reference=None,
            source="CUSTOMER_CHAT",
            created_by_persona="CUSTOMER",
            created_at=_NOW,
            updated_at=_NOW,
            policy_version="policy-v1",
            version=1,
        )
    )
    await session.commit()

    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=None)],
    )

    result = _send(arrangement_client, conversation_id, customer_headers, "I want a payment plan")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is None
    content = body["assistant_message"]["content"].lower()
    assert "amend" in content
    assert "cancel" in content
    assert "human" in content


# AC4 -------------------------------------------------------------------


async def test_rules_engine_failure_escalates_ambiguous_validation_with_no_options_offered(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """A fresh, never-activated `PolicyProvider` fails `get_active()` closed
    -- `api/deps.py`'s own `_FALLBACK_POLICY_PROVIDER` documents this exact
    degrade-to-`PolicyUnavailable` behavior."""
    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=None)],
    )
    arrangement_client.app.state.policy_provider = PolicyProvider()

    result = _send(arrangement_client, conversation_id, customer_headers, "I want a payment plan")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is None
    assert "specialist" in body["assistant_message"]["content"].lower()

    cases = (await session.execute(select(EscalationCaseOrm))).scalars().all()
    ambiguous = [c for c in cases if c.reason == "AMBIGUOUS_VALIDATION"]
    assert len(ambiguous) == 1

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert rows == []


# AC7 -------------------------------------------------------------------


async def test_off_menu_installment_count_is_never_offered_and_escalates_exceptional(
    arrangement_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(arrangement_client, customer_headers)
    _script(
        arrangement_client,
        # policy-v1's standard counts are 3, 6, 12 -- 7 is off-menu.
        [_intent_response("PAYMENT_PLAN"), _extraction_response(installment_count=7)],
    )

    result = _send(arrangement_client, conversation_id, customer_headers, "7 payments please")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["proposal"] is None
    assert "specialist" in body["assistant_message"]["content"].lower()

    cases = (
        (await session.execute(select(EscalationCaseOrm))).scalars().all()
    )
    exceptional = [c for c in cases if c.reason == "EXCEPTIONAL_ARRANGEMENT"]
    assert len(exceptional) == 1
    assert exceptional[0].queue == "COLLECTIONS_EXCEPTION_REVIEW"

    rows = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert rows == []
