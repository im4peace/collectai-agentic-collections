"""E7-S3 AC2, AC3, AC6 (object-level half): `GET /api/escalations/{case_id}`,
end to end against a real, migrated Postgres database. Mirrors
`test_e7_s5_compliance_decision.py`'s fixtures and `_seed_case` helper.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_detail01"
_ACCOUNT_ID = "acc_detail01"
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}
_COMPLIANCE_HEADERS = {"X-Persona": Persona.COMPLIANCE_RISK.value}


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


async def _seed_case(
    session: AsyncSession,
    *,
    case_id: str,
    queue: str = "COLLECTIONS_REVIEW",
    reviewer_role: str = "COLLECTIONS_OFFICER",
    status: str = "OPEN",
    conversation_id: str | None = None,
    recommendation_id: str | None = None,
    exception_types: list[str] | None = None,
    requested_terms: dict[str, object] | None = None,
    dispute_id: str | None = None,
) -> None:
    session.add(
        EscalationCaseOrm(
            case_id=case_id,
            customer_id=_CUSTOMER_ID,
            account_id=_ACCOUNT_ID,
            conversation_id=conversation_id,
            item_id=None,
            reason="REQUEST_HUMAN" if exception_types is None else "EXCEPTIONAL_ARRANGEMENT",
            queue=queue,
            reviewer_role=reviewer_role,
            priority="ELEVATED",
            status=status,
            source="AI",
            summary="Customer requested a specialist review.",
            requested_terms=requested_terms,
            exception_types=exception_types,
            hardship_case_id=None,
            dispute_id=dispute_id,
            recommendation_id=recommendation_id,
            parent_case_id=None,
            rerouted_to_case_id=None,
            routing_policy_version="policy-v1",
            routing_flags=["MANDATORY_ESCALATION"],
            first_reviewed_at=None,
            created_at=_NOW,
            decided_at=None,
            updated_at=_NOW,
            version=1,
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
                display_name="Layla Haddad",
                email=f"{_CUSTOMER_ID}@example.com",
                phone="+971-50-1112222",
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
        db_session.add(
            ConversationOrm(
                conversation_id="conv_detail_1",
                customer_id=_CUSTOMER_ID,
                account_id=_ACCOUNT_ID,
                status="HANDED_OFF",
                clarification_count=0,
                created_at=_NOW,
                last_message_at=_NOW,
            )
        )
        await db_session.flush()
        db_session.add(
            ChatMessageOrm(
                message_id="msg_detail_1",
                conversation_id="conv_detail_1",
                customer_id=_CUSTOMER_ID,
                turn_id=None,
                role="CUSTOMER",
                content="I need to talk to someone about my account.",
                content_source="CUSTOMER_INPUT",
                labels=[],
                created_at=_NOW,
            )
        )
        db_session.add(
            RecommendationOrm(
                recommendation_id="rec_detail_1",
                account_id=_ACCOUNT_ID,
                customer_id=_CUSTOMER_ID,
                action="ESCALATE_TO_HUMAN_REVIEW",
                rationale="Customer explicitly asked for a human.",
                referenced_factor_ids=[],
                status="GENERATED",
                content_source="MODEL",
                model_id="mock-model",
                prompt_version="p1",
                policy_version="policy-v1",
                record_version=1,
                correlation_id="corr-detail-1",
                created_at=_NOW,
                audit_event_id="aud_detail_1",
                officer_decision=None,
                officer_decision_reason=None,
                officer_chosen_action=None,
                decided_by_persona=None,
                decided_at=None,
            )
        )
        await db_session.commit()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(_NOW)


@pytest.fixture
def detail_client(
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
    with TestClient(app) as client:
        yield client


# AC2 -------------------------------------------------------------------


async def test_case_detail_returns_conversation_recommendation_and_rule_results(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(
        session,
        case_id="esc_detail_ac2",
        conversation_id="conv_detail_1",
        recommendation_id="rec_detail_1",
        exception_types=["TERM"],
        requested_terms={"installment_count": 6},
    )

    response = detail_client.get("/api/escalations/esc_detail_ac2", headers=_OFFICER_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["case_id"] == "esc_detail_ac2"
    assert len(body["conversation"]) == 1
    assert body["conversation"][0]["content"] == "I need to talk to someone about my account."

    assert body["ai_recommendation"] is not None
    assert body["ai_recommendation"]["recommendation_id"] == "rec_detail_1"
    assert body["ai_recommendation"]["action"] == "ESCALATE_TO_HUMAN_REVIEW"

    assert body["rule_results"]["summary"] == "Customer requested a specialist review."
    assert body["rule_results"]["exception_types"] == ["TERM"]
    assert body["rule_results"]["requested_terms"] == {"installment_count": 6}
    assert body["rule_results"]["routing_flags"] == ["MANDATORY_ESCALATION"]
    assert body["rule_results"]["routing_policy_version"] == "policy-v1"


async def test_case_detail_with_no_conversation_or_recommendation_returns_empty_sections(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_detail_ac2_empty")

    response = detail_client.get(
        "/api/escalations/esc_detail_ac2_empty", headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation"] == []
    assert body["ai_recommendation"] is None


# AC3 -------------------------------------------------------------------


async def test_approve_permitted_true_for_an_ordinary_actionable_officer_case(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_detail_ac3_true")

    response = detail_client.get("/api/escalations/esc_detail_ac3_true", headers=_OFFICER_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["approve_permitted"] is True


async def test_approve_permitted_false_for_an_already_decided_case(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_detail_ac3_decided", status="DECIDED")

    response = detail_client.get(
        "/api/escalations/esc_detail_ac3_decided", headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200, response.text
    assert response.json()["approve_permitted"] is False


async def test_approve_permitted_false_for_compliance_risk_viewer(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(
        session,
        case_id="esc_detail_ac3_compliance",
        queue="COMPLIANCE_REVIEW",
        reviewer_role="COMPLIANCE_RISK",
    )

    response = detail_client.get(
        "/api/escalations/esc_detail_ac3_compliance", headers=_COMPLIANCE_HEADERS
    )
    assert response.status_code == 200, response.text
    assert response.json()["approve_permitted"] is False


# AC6 (object-level half) ------------------------------------------------


async def test_compliance_risk_cannot_open_a_collections_review_case_detail(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_detail_ac6_officer_case")

    response = detail_client.get(
        "/api/escalations/esc_detail_ac6_officer_case", headers=_COMPLIANCE_HEADERS
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["reason_code"] == "QUEUE_NOT_PERMITTED"


async def test_officer_can_open_a_compliance_review_case_detail_read_only(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(
        session,
        case_id="esc_detail_ac6_compliance_case",
        queue="COMPLIANCE_REVIEW",
        reviewer_role="COMPLIANCE_RISK",
    )

    response = detail_client.get(
        "/api/escalations/esc_detail_ac6_compliance_case", headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200, response.text
    assert response.json()["queue"] == "COMPLIANCE_REVIEW"


# Not found ----------------------------------------------------------------


async def test_unknown_case_id_returns_404(
    detail_client: TestClient, session: AsyncSession
) -> None:
    del session
    response = detail_client.get("/api/escalations/esc_does_not_exist", headers=_OFFICER_HEADERS)
    assert response.status_code == 404, response.text


# Group K (E11-S4 AC3): the additive `dispute` block ----------------------------


async def _seed_dispute(session: AsyncSession, dispute_id: str) -> None:
    session.add(
        DisputeOrm(
            dispute_id=dispute_id,
            account_id=_ACCOUNT_ID,
            customer_id=_CUSTOMER_ID,
            item_id=None,
            category="NOT_MY_DEBT",
            customer_reason="This is not my debt.",
            status="OPEN",
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


async def test_dispute_case_detail_includes_the_linked_dispute_for_an_officer(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_dispute(session, "dsp_detail_1")
    await _seed_case(
        session,
        case_id="esc_detail_dispute",
        queue="DISPUTE_REVIEW",
        dispute_id="dsp_detail_1",
    )

    response = detail_client.get("/api/escalations/esc_detail_dispute", headers=_OFFICER_HEADERS)

    assert response.status_code == 200, response.text
    dispute = response.json()["dispute"]
    assert dispute["dispute_id"] == "dsp_detail_1"
    assert dispute["status"] == "OPEN"
    assert dispute["category"] == "NOT_MY_DEBT"
    assert dispute["version"] == 1
    assert dispute["outcome"] is None


async def test_case_detail_without_a_dispute_has_a_null_dispute_block(
    detail_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_detail_no_dispute")

    response = detail_client.get("/api/escalations/esc_detail_no_dispute", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    assert response.json()["dispute"] is None


async def test_dispute_block_is_never_shown_to_compliance_risk(
    detail_client: TestClient, session: AsyncSession
) -> None:
    """`dispute:read` is officer-only (`api/rbac.py`); the case-detail read
    must not become a side door to dispute data for another persona."""
    await _seed_dispute(session, "dsp_detail_2")
    await _seed_case(
        session,
        case_id="esc_detail_dispute_compliance",
        queue="COMPLIANCE_REVIEW",
        reviewer_role="COMPLIANCE_RISK",
        dispute_id="dsp_detail_2",
    )

    response = detail_client.get(
        "/api/escalations/esc_detail_dispute_compliance", headers=_COMPLIANCE_HEADERS
    )

    assert response.status_code == 200, response.text
    assert response.json()["dispute"] is None
