"""E8-S2 AC1-AC6: financial-hardship identification and handling, end to
end against a real, migrated Postgres database. Mirrors
`test_e8_s3_dispute_flow.py`'s fixtures and helper shape; `_decide` mirrors
`test_e7_s4_exceptional_arrangement.py`'s own helper.
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
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    HardshipIndicatorType,
    LlmMode,
    Persona,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_820101"
_ACCOUNT_ID = "acc_820201"
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
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        await _ensure_policy_rule_set_row(db_session)
        db_session.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Omar Haddad",
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
def hardship_client(
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
def customer_headers(hardship_client: TestClient) -> dict[str, str]:
    response = hardship_client.post(
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


def _hardship_extraction_response(*, indicator_types: list[str]) -> ProviderResult:
    content = json.dumps({"indicator_types": indicator_types})
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


async def _report_hardship(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> tuple[str, EscalationCaseOrm]:
    """Drives the real chat flow to open a FINANCIAL_HARDSHIP case. Returns
    `(conversation_id, case)`."""
    conversation_id = _create_conversation(hardship_client, customer_headers)
    _script(
        hardship_client,
        [
            _intent_response("FINANCIAL_HARDSHIP"),
            _hardship_extraction_response(indicator_types=["JOB_LOSS"]),
        ],
    )
    result = _send(hardship_client, conversation_id, customer_headers, "I lost my job last week")
    assert result.status_code == 200, result.text

    cases = (await session.execute(select(EscalationCaseOrm))).scalars().all()
    hardship_cases = [c for c in cases if c.reason == "FINANCIAL_HARDSHIP"]
    assert len(hardship_cases) == 1
    return conversation_id, hardship_cases[0]


# AC1 ---------------------------------------------------------------------


async def test_hardship_message_opens_a_hardship_case_and_a_real_escalation(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id, case = await _report_hardship(hardship_client, customer_headers, session)
    assert case.status == "OPEN"
    assert case.queue == "HARDSHIP_REVIEW"
    assert case.reviewer_role == "COLLECTIONS_OFFICER"
    assert case.conversation_id == conversation_id

    rows = (await session.execute(select(HardshipCaseOrm))).scalars().all()
    assert len(rows) == 1
    assert rows[0].account_id == _ACCOUNT_ID
    assert rows[0].status == "OPEN"
    assert rows[0].indicators == [
        {"indicator_type": "JOB_LOSS", "customer_statement": "I lost my job last week"}
    ]
    assert rows[0].escalation_case_id == case.case_id
    assert case.hardship_case_id == rows[0].hardship_case_id


async def test_no_indicators_extracted_still_records_a_case_with_other(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """A hardship report is always recorded, even when the model finds no
    specific indicator type -- `[OTHER]`, never an empty/missing list (the
    table's own `CHECK (jsonb_array_length(indicators) >= 1)`)."""
    conversation_id = _create_conversation(hardship_client, customer_headers)
    _script(
        hardship_client,
        [_intent_response("FINANCIAL_HARDSHIP"), _hardship_extraction_response(indicator_types=[])],
    )
    result = _send(hardship_client, conversation_id, customer_headers, "Things are hard right now")
    assert result.status_code == 200, result.text

    rows = (await session.execute(select(HardshipCaseOrm))).scalars().all()
    assert len(rows) == 1
    assert rows[0].indicators == [
        {"indicator_type": "OTHER", "customer_statement": "Things are hard right now"}
    ]


# AC2 -----------------------------------------------------------------------

_FORBIDDEN_WORDS = (
    "approved",
    "we will reduce",
    "reduced your",
    "waived",
    "forgiven",
    "restructured",
    "relief granted",
    "lowered your payment",
)

_SCRIPTED_HARDSHIP_MESSAGES: list[tuple[str, list[str]]] = [
    ("I lost my job last week", ["JOB_LOSS"]),
    ("My hours got cut and I'm earning less", ["INCOME_REDUCTION"]),
    ("My mother is sick and I've been paying medical bills", ["MEDICAL_OR_FAMILY_EMERGENCY"]),
    ("I'm just short on cash this month", ["TEMPORARY_FINANCIAL_DIFFICULTY"]),
    ("Things have been difficult for me lately", ["OTHER"]),
    ("I was laid off from my company", ["JOB_LOSS"]),
    ("My pay was reduced by my employer", ["INCOME_REDUCTION"]),
    ("There's been a family emergency and hospital costs", ["MEDICAL_OR_FAMILY_EMERGENCY"]),
    ("Just a temporary cash flow problem for me", ["TEMPORARY_FINANCIAL_DIFFICULTY"]),
    ("I'm struggling financially right now", ["OTHER"]),
    ("I got fired unexpectedly", ["JOB_LOSS"]),
    ("My hours at work were cut in half", ["INCOME_REDUCTION"]),
    ("My father passed away and there were costs", ["MEDICAL_OR_FAMILY_EMERGENCY"]),
    ("I'm in a tight spot financially this month", ["TEMPORARY_FINANCIAL_DIFFICULTY"]),
    ("Life has been tough on me financially", ["OTHER"]),
    ("My employer let me go", ["JOB_LOSS"]),
    ("I'm making a lot less money now", ["INCOME_REDUCTION"]),
    ("I've had a medical emergency recently", ["MEDICAL_OR_FAMILY_EMERGENCY"]),
    ("I need a bit more time, cash is tight", ["TEMPORARY_FINANCIAL_DIFFICULTY"]),
    ("I'm dealing with a hardship right now", []),
]


@pytest.mark.parametrize("content,indicator_types", _SCRIPTED_HARDSHIP_MESSAGES)
def test_ac2_guardrail_no_ai_reply_ever_promises_relief_or_restructuring(
    hardship_client: TestClient,
    customer_headers: dict[str, str],
    content: str,
    indicator_types: list[str],
) -> None:
    """AC2: 20 scripted hardship cases, zero critical policy violations --
    every reply is `_chat_reply_planning`'s fixed, pre-written template
    (`customer_message_for(EscalationReason.FINANCIAL_HARDSHIP)`), so no
    wording the model chooses ever reaches the customer at all."""
    conversation_id = _create_conversation(hardship_client, customer_headers)
    _script(
        hardship_client,
        [
            _intent_response("FINANCIAL_HARDSHIP"),
            _hardship_extraction_response(indicator_types=indicator_types),
        ],
    )

    result = _send(hardship_client, conversation_id, customer_headers, content)
    assert result.status_code == 200, result.text
    reply = result.json()["assistant_message"]["content"].lower()
    for forbidden in _FORBIDDEN_WORDS:
        assert forbidden not in reply, f"{forbidden!r} found in reply for {content!r}"


# AC3 -------------------------------------------------------------------


async def test_open_hardship_case_suppresses_automated_treatment_for_the_account(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC3: automated recommendations/outreach are suppressed for the whole
    account (`hardship_scope: "ACCOUNT"`) until a human decision, derived
    live by `customer360_service` from the OPEN `EscalationCase` this
    module's own chat flow just created -- no separate flag to set."""
    await _report_hardship(hardship_client, customer_headers, session)

    response = hardship_client.get(
        f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200, response.text
    treatment = response.json()["deterministic"]["treatment"]
    assert treatment["automated_treatment_suppressed"] is True


# AC4 -------------------------------------------------------------------


async def test_hardship_case_has_elevated_priority_and_is_visible_in_the_queue(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id, case = await _report_hardship(hardship_client, customer_headers, session)
    assert case.priority == "ELEVATED"

    response = hardship_client.get(
        "/api/escalations", params={"queue": "HARDSHIP_REVIEW"}, headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    matching = [item for item in items if item["case_id"] == case.case_id]
    assert len(matching) == 1
    assert matching[0]["priority"] == "ELEVATED"
    assert matching[0]["account_id"] == _ACCOUNT_ID

    customer_360 = hardship_client.get(
        f"/api/customers/{_ACCOUNT_ID}/360", headers=_OFFICER_HEADERS
    )
    assert customer_360.status_code == 200, customer_360.text


# AC5 -------------------------------------------------------------------


async def test_repeated_hardship_message_for_the_same_account_returns_the_existing_case(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    conversation_id = _create_conversation(hardship_client, customer_headers)
    _script(
        hardship_client,
        [
            _intent_response("FINANCIAL_HARDSHIP"),
            _hardship_extraction_response(indicator_types=["JOB_LOSS"]),
            _intent_response("FINANCIAL_HARDSHIP"),
            _hardship_extraction_response(indicator_types=["INCOME_REDUCTION"]),
        ],
    )

    first = _send(hardship_client, conversation_id, customer_headers, "I lost my job")
    assert first.status_code == 200, first.text

    second = _send(hardship_client, conversation_id, customer_headers, "My income also dropped")
    assert second.status_code == 200, second.text

    rows = (await session.execute(select(HardshipCaseOrm))).scalars().all()
    assert len(rows) == 1
    # The second message never overwrites the first case's own indicators.
    assert rows[0].indicators == [
        {"indicator_type": "JOB_LOSS", "customer_statement": "I lost my job"}
    ]


async def test_hardship_service_idempotency_key_replay_returns_the_same_case(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC5's other clause, exercised directly against `hardship_service`
    (not reachable via the chat endpoint, which sends no `Idempotency-Key`
    header -- mirrors `dispute_service`'s own equivalent test)."""
    from collectai.audit.service import AuditService
    from collectai.config.policy.loader import load_seed_policy_v1
    from collectai.config.policy.provider import PolicyProvider
    from collectai.domain_services.hardship_service import create_hardship_from_chat

    conversation_id = _create_conversation(hardship_client, customer_headers)
    clock = SimulatedClock(_NOW)
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    audit_service = AuditService(clock, async_sessionmaker(session.bind, expire_on_commit=False))

    first = await create_hardship_from_chat(
        session,
        conversation_id=conversation_id,
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        indicator_types=[HardshipIndicatorType.JOB_LOSS],
        customer_statement="I lost my job",
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id="corr-hardship-1",
        idempotency_key="hardship-key-0001",
    )
    await session.commit()
    assert first.created is True

    second = await create_hardship_from_chat(
        session,
        conversation_id=conversation_id,
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        indicator_types=[HardshipIndicatorType.JOB_LOSS],
        customer_statement="I lost my job",
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id="corr-hardship-2",
        idempotency_key="hardship-key-0001",
    )
    await session.commit()
    assert second.created is False
    assert second.hardship_case.hardship_case_id == first.hardship_case.hardship_case_id

    rows = (await session.execute(select(HardshipCaseOrm))).scalars().all()
    assert len(rows) == 1


# AC6 -------------------------------------------------------------------


async def test_officer_can_approve_a_hardship_case_with_no_financial_change(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC6: the reviewer records a decision; APPROVE of a HARDSHIP_REVIEW
    case never executes a restructuring or other financial-state change --
    `review_service.decide` writes no `PaymentArrangement` row for any case
    whose reason is not EXCEPTIONAL_ARRANGEMENT."""
    _, case = await _report_hardship(hardship_client, customer_headers, session)

    response = _decide(
        hardship_client,
        case.case_id,
        {
            "action": "APPROVE",
            "expected_version": 1,
            "reason": "Hardship confirmed, noted on file.",
        },
        idempotency_key="ac6-a",
    )
    assert response.status_code == 201, response.text
    assert response.json()["arrangement"] is None

    arrangements = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert arrangements == []


async def test_officer_can_reroute_a_hardship_case_to_policy_exception(
    hardship_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """AC6: "requests for restructuring or policy exception recorded as
    decisions or re-routed" -- ESCALATE with reason POLICY_EXCEPTION is one
    of `policy-v1.json`'s own `reviewer_escalation_reasons`."""
    _, case = await _report_hardship(hardship_client, customer_headers, session)

    response = _decide(
        hardship_client,
        case.case_id,
        {
            "action": "ESCALATE",
            "expected_version": 1,
            "reason": "Needs a policy exception to restructure.",
            "escalate_reason": "POLICY_EXCEPTION",
        },
        idempotency_key="ac6-b",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["case_status"] == "RE_ROUTED"
    assert body["rerouted_case_id"] is not None

    arrangements = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    assert arrangements == []

    rerouted = await session.get(EscalationCaseOrm, body["rerouted_case_id"])
    assert rerouted is not None
    assert rerouted.reason == "POLICY_EXCEPTION"
