"""E8-S3 AC2, AC3, AC5: the dispute guardrail (no AI output judges validity),
disputed-item blocking of arrangement creation, and dispute-creation
idempotency, end to end against a real, migrated Postgres database. AC1/AC4
(a dispute message opens a real Dispute + DISPUTE_REVIEW escalation) are
covered by `test_e6_s1_chat_api.py`'s own
`test_dispute_intent_opens_a_dispute_and_a_real_escalation`. Mirrors
`test_e8_s1_arrangement_flow.py`'s fixtures and helper shape.
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
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    DisputeCategory,
    LlmMode,
    Persona,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_800301"
_ACCOUNT_ID = "acc_800401"


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
                display_name="Nadia Petrov",
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
def dispute_client(
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
def customer_headers(dispute_client: TestClient) -> dict[str, str]:
    response = dispute_client.post(
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


def _dispute_extraction_response(*, category: str | None) -> ProviderResult:
    content = json.dumps({"category": category})
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


_JUDGING_WORDS = (
    "valid",
    "invalid",
    "confirmed",
    "you're right",
    "you are right",
    "we agree",
    "that's correct",
    "that's incorrect",
    "denied",
    "approved",
)

_SCRIPTED_DISPUTE_MESSAGES: list[tuple[str, str | None]] = [
    ("This charge isn't mine", "NOT_MY_DEBT"),
    ("I already paid this last month", "ALREADY_PAID"),
    ("The amount is wrong, it should be lower", "AMOUNT_INCORRECT"),
    ("Someone used my card without permission", "FRAUD_OR_UNAUTHORIZED"),
    ("This interest fee shouldn't be here", "FEE_OR_INTEREST_DISPUTE"),
    ("I don't think this is right at all", "OTHER"),
    ("That's not my debt, I never opened this account", "NOT_MY_DEBT"),
    ("I paid this in full, check your records", "ALREADY_PAID"),
    ("Your amount is incorrect compared to my statement", "AMOUNT_INCORRECT"),
    ("This was fraud, I never authorized it", "FRAUD_OR_UNAUTHORIZED"),
    ("Why is there an extra fee here", "FEE_OR_INTEREST_DISPUTE"),
    ("Something about this bill seems off", "OTHER"),
    ("This debt belongs to someone else", "NOT_MY_DEBT"),
    ("I settled this account already", "ALREADY_PAID"),
    ("The balance you show is too high", "AMOUNT_INCORRECT"),
    ("My card was stolen and used here", "FRAUD_OR_UNAUTHORIZED"),
    ("The interest charge looks miscalculated", "FEE_OR_INTEREST_DISPUTE"),
    ("I want to dispute this whole thing", None),
    ("Not my account, never signed up", "NOT_MY_DEBT"),
    ("I have a receipt showing I paid", "ALREADY_PAID"),
]


@pytest.mark.parametrize("content,category", _SCRIPTED_DISPUTE_MESSAGES)
def test_ac2_guardrail_no_ai_reply_ever_states_or_implies_validity(
    dispute_client: TestClient,
    customer_headers: dict[str, str],
    content: str,
    category: str | None,
) -> None:
    """AC2: 20 scripted dispute cases, zero critical policy violations --
    every reply is `_chat_reply_planning`'s fixed, pre-written template
    (`customer_message_for(EscalationReason.DISPUTE)`), so no wording the
    model chooses ever reaches the customer at all."""
    conversation_id = _create_conversation(dispute_client, customer_headers)
    _script(
        dispute_client,
        [_intent_response("DISPUTE"), _dispute_extraction_response(category=category)],
    )

    result = _send(dispute_client, conversation_id, customer_headers, content)
    assert result.status_code == 200, result.text
    reply = result.json()["assistant_message"]["content"].lower()
    for judging_word in _JUDGING_WORDS:
        assert judging_word not in reply, f"{judging_word!r} found in reply for {content!r}"


# AC5 -------------------------------------------------------------------


async def test_repeated_dispute_message_for_the_same_item_returns_the_existing_dispute(
    dispute_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(dispute_client, customer_headers)
    _script(
        dispute_client,
        [
            _intent_response("DISPUTE"),
            _dispute_extraction_response(category="AMOUNT_INCORRECT"),
            _intent_response("DISPUTE"),
            _dispute_extraction_response(category="NOT_MY_DEBT"),
        ],
    )

    first = _send(dispute_client, conversation_id, customer_headers, "This amount is wrong")
    assert first.status_code == 200, first.text

    second = _send(dispute_client, conversation_id, customer_headers, "This still isn't right")
    assert second.status_code == 200, second.text

    disputes = (await session.execute(select(DisputeOrm))).scalars().all()
    assert len(disputes) == 1
    # The second message never overwrites the first dispute's own category.
    assert disputes[0].category == DisputeCategory.AMOUNT_INCORRECT.value


async def test_dispute_service_idempotency_key_replay_returns_the_same_dispute(
    dispute_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC5's other clause, exercised directly against `dispute_service`
    (not reachable via the chat endpoint, which sends no `Idempotency-Key`
    header -- see `dispute_service.create_dispute_from_chat`'s own
    docstring): the same `idempotency_key` returns the original dispute and
    creates no second row."""
    from collectai.audit.service import AuditService
    from collectai.config.policy.loader import load_seed_policy_v1
    from collectai.config.policy.provider import PolicyProvider
    from collectai.domain_services.dispute_service import create_dispute_from_chat

    conversation_id = _create_conversation(dispute_client, customer_headers)
    clock = SimulatedClock(_NOW)
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    audit_service = AuditService(clock, async_sessionmaker(session.bind, expire_on_commit=False))

    first = await create_dispute_from_chat(
        session,
        conversation_id=conversation_id,
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        item_id=None,
        category=DisputeCategory.FRAUD_OR_UNAUTHORIZED,
        customer_reason="Unauthorized charge",
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id="corr-dispute-1",
        idempotency_key="dispute-key-0001",
    )
    await session.commit()
    assert first.created is True

    second = await create_dispute_from_chat(
        session,
        conversation_id=conversation_id,
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        item_id=None,
        category=DisputeCategory.FRAUD_OR_UNAUTHORIZED,
        customer_reason="Unauthorized charge",
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id="corr-dispute-2",
        idempotency_key="dispute-key-0001",
    )
    await session.commit()
    assert second.created is False
    assert second.dispute.dispute_id == first.dispute.dispute_id

    disputes = (
        (await session.execute(select(DisputeOrm).where(DisputeOrm.item_id.is_(None))))
        .scalars()
        .all()
    )
    assert len(disputes) == 1


# AC3 -------------------------------------------------------------------


async def test_open_dispute_blocks_confirming_an_arrangement_with_disputed_item(
    dispute_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC3: an arrangement offered before the dispute was opened still
    cannot be *confirmed* afterwards -- `arrangement_service` revalidates
    at confirm time, mirroring PTP's own existing `DISPUTED_ITEM` block
    (`test_e6_s6_manual_ptp_api.py`)."""
    conversation_id = _create_conversation(dispute_client, customer_headers)
    arrangement_extraction = ProviderResult(
        content=json.dumps(
            {
                "promised_amount": None,
                "promised_date": None,
                "payment_option": None,
                "installment_count": 3,
            }
        ),
        model_id="mock-model-1",
        latency_ms=5.0,
    )
    _script(dispute_client, [_intent_response("PAYMENT_PLAN"), arrangement_extraction])
    offer = _send(dispute_client, conversation_id, customer_headers, "3 payments please")
    assert offer.status_code == 200, offer.text
    proposal = offer.json()["proposal"]
    assert proposal is not None

    from collectai.audit.service import AuditService
    from collectai.config.policy.loader import load_seed_policy_v1
    from collectai.config.policy.provider import PolicyProvider
    from collectai.domain_services.dispute_service import create_dispute_from_chat

    clock = SimulatedClock(_NOW)
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    audit_service = AuditService(clock, async_sessionmaker(session.bind, expire_on_commit=False))
    await create_dispute_from_chat(
        session,
        conversation_id=conversation_id,
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        item_id=None,
        category=DisputeCategory.AMOUNT_INCORRECT,
        customer_reason="This amount is wrong",
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id="corr-dispute-block",
    )
    await session.commit()

    confirm_headers = dict(customer_headers)
    confirm_headers["Idempotency-Key"] = "confirm-blocked-0001"
    confirm = dispute_client.post(
        f"/api/chat/conversations/{conversation_id}/proposals/{proposal['proposal_id']}/confirm",
        json={"terms_hash": proposal["terms_hash"]},
        headers=confirm_headers,
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["error"]["reason_code"] == "DISPUTED_ITEM"
