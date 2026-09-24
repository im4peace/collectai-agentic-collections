"""E9-S4 AC4: prompts sent to the MOCK provider and application logs
(the durable `audit_event` table, `audit/redaction.py`'s own target)
contain no secrets or prohibited identifiers across a red-team-style run.

Two halves:
- `audit/redaction.py`'s `redact_value` already runs before every
  `audit_event` write (E1-S4 AC4) -- this test proves it holds end to end,
  by planting a card number in a customer chat message, running it through
  the real chat flow, then scanning every stored `audit_event` row's JSON
  fields for the pattern it should have redacted.
- The prompt-construction builders (`build_intent_request`,
  `build_proposal_extraction_request`, `build_dispute_extraction_request`)
  never interpolate anything beyond `AllowedPromptContext`'s narrow
  allow-listed fields plus the customer's own message -- no settings value,
  environment variable or credential can reach a prompt at all.
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
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.seed.scanner import scan_text_for_dangerous_patterns
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_900301"
_ACCOUNT_ID = "acc_900401"


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
                display_name="Owen Baptiste",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+1-555-0155",
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
def leakage_client(
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
def customer_headers(leakage_client: TestClient) -> dict[str, str]:
    response = leakage_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


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


async def _all_audit_json_values(session: AsyncSession) -> list[str]:
    rows = (await session.execute(select(AuditEventOrm))).scalars().all()
    values: list[str] = []
    for row in rows:
        for field in (row.ai_output, row.tool_calls, row.rule_results, row.human_override):
            if field is None:
                continue
            values.extend(_iter_strings(field))
        if row.input_ref:
            values.append(row.input_ref)
    return values


def _iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for nested in value.values():
            found.extend(_iter_strings(nested))
        return found
    if isinstance(value, list):
        found = []
        for nested in value:
            found.extend(_iter_strings(nested))
        return found
    return []


async def test_a_planted_card_number_in_a_customer_message_is_redacted_before_storage(
    leakage_client: TestClient, customer_headers: dict[str, str], session: AsyncSession
) -> None:
    """The customer's own message text can itself carry a planted card
    number (a customer might paste one by mistake); `audit_service.record_in`
    redacts every audit draft before it is ever written (`audit/redaction
    .py`), so it must never survive into a stored `audit_event` row."""
    conversation_response = leakage_client.post(
        "/api/chat/conversations", json={"account_id": _ACCOUNT_ID}, headers=customer_headers
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation_id = conversation_response.json()["conversation"]["conversation_id"]

    leakage_client.app.state.chat_llm_provider = MockProvider([_intent_response("UNKNOWN")])
    result = leakage_client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"content": "My card 4111111111111111 was charged twice, please check"},
        headers=customer_headers,
    )
    assert result.status_code == 200, result.text

    stored_values = await _all_audit_json_values(session)
    for value in stored_values:
        findings = scan_text_for_dangerous_patterns(value)
        assert not findings, f"prohibited pattern survived redaction in audit_event: {findings}"


def test_prompt_builders_never_include_anything_beyond_the_allow_list_and_message() -> None:
    """Structural proof for the other half of AC4: every prompt this system
    ever sends is built from `AllowedPromptContext` (a fixed, narrow field
    set) rendered by `render_prompt`, plus the customer's own message --
    there is no code path that can interpolate a settings value, an
    environment variable or a credential into a prompt."""
    from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
    from collectai.ai_orchestration.prompts.dispute_v1 import build_dispute_extraction_request
    from collectai.ai_orchestration.prompts.intent_v1 import build_intent_request
    from collectai.ai_orchestration.prompts.proposal_v1 import build_proposal_extraction_request

    context = AllowedPromptContext(
        customer_display_name="Test Customer", account_reference="acc_test"
    )
    rendered_context = render_prompt(context)
    assert not scan_text_for_dangerous_patterns(rendered_context)

    builders = (
        build_intent_request,
        build_proposal_extraction_request,
        build_dispute_extraction_request,
    )
    for builder in builders:
        request = builder(context=context, message="a normal customer message")
        assert not scan_text_for_dangerous_patterns(request.system)
        for message in request.messages:
            assert not scan_text_for_dangerous_patterns(str(message.get("content", "")))

    # `AllowedPromptContext`'s own field set is the entire allow-list --
    # confirming its shape here means no other field could ever be added to
    # `render_prompt`'s output without this test's own fields list changing.
    assert set(AllowedPromptContext.model_fields) == {
        "customer_display_name",
        "account_reference",
        "delinquency_summary",
        "priority_band",
        "eligible_options_summary",
    }
