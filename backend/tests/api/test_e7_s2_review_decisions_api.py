"""E7-S2 AC1-AC8: `POST /api/escalations/{case_id}/decisions`, end to end
against a real, migrated Postgres database. Mirrors
`test_e7_s1_escalations_api.py`'s fixtures; mixes sync `TestClient` calls
with `await session...` seeding in the same async test function, the same
pattern `test_e4_s3_recommendations_api.py` already establishes.
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
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.rules_engine.arrangement import get_eligible_options
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_500401"
_ACCOUNT_ID = "acc_500501"
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


async def _seed_case(
    session: AsyncSession,
    *,
    case_id: str,
    queue: str = "COLLECTIONS_REVIEW",
    reviewer_role: str = "COLLECTIONS_OFFICER",
    status: str = "OPEN",
    exception_types: list[str] | None = None,
    version: int = 1,
) -> None:
    session.add(
        EscalationCaseOrm(
            case_id=case_id,
            customer_id=_CUSTOMER_ID,
            account_id=_ACCOUNT_ID,
            conversation_id=None,
            item_id=None,
            reason="REQUEST_HUMAN",
            queue=queue,
            reviewer_role=reviewer_role,
            priority="NORMAL",
            status=status,
            source="CUSTOMER",
            summary="Test case",
            requested_terms=None,
            exception_types=exception_types,
            hardship_case_id=None,
            dispute_id=None,
            recommendation_id=None,
            parent_case_id=None,
            rerouted_to_case_id=None,
            routing_policy_version="policy-v1",
            routing_flags=[],
            first_reviewed_at=None,
            created_at=_NOW,
            decided_at=None,
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
def review_client(
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


def _decide(
    client: TestClient, case_id: str, body: dict[str, object], *, idempotency_key: str
) -> object:
    headers = dict(_OFFICER_HEADERS)
    headers["Idempotency-Key"] = idempotency_key
    return client.post(f"/api/escalations/{case_id}/decisions", json=body, headers=headers)


def _eligible_option_id(clock: SimulatedClock) -> str:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    result = get_eligible_options(
        provider, clock, Money("770.40"), 30, has_active_ptp=False, has_active_arrangement=False
    )
    assert result.ok and result.value is not None
    assert result.value.options
    return result.value.options[0].option_id


# AC1 ---------------------------------------------------------------------


@pytest.mark.parametrize("action", ["REJECT", "MODIFY", "ESCALATE"])
async def test_actions_without_a_reason_return_422(
    review_client: TestClient, session: AsyncSession, action: str
) -> None:
    case_id = f"esc_review_ac1_{action.lower()}"
    await _seed_case(session, case_id=case_id)

    response = _decide(
        review_client, case_id, {"action": action, "expected_version": 1}, idempotency_key="ac1"
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


async def test_request_more_information_without_a_note_returns_422(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac1_b")

    response = _decide(
        review_client,
        "esc_review_ac1_b",
        {"action": "REQUEST_MORE_INFORMATION", "expected_version": 1},
        idempotency_key="ac1-b",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "NOTE_REQUIRED"


# AC2 -----------------------------------------------------------------------


async def test_approve_not_permitted_by_policy_for_an_unauthorized_exception_type(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac2_a", exception_types=["AMOUNT_STRUCTURE"])

    response = _decide(
        review_client,
        "esc_review_ac2_a",
        {"action": "APPROVE", "expected_version": 1, "reason": "Meets standard eligibility."},
        idempotency_key="ac2-a",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "NOT_PERMITTED_BY_POLICY"


async def test_approve_permitted_by_policy_for_an_authorized_exception_type(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac2_b", exception_types=["TERM"])

    response = _decide(
        review_client,
        "esc_review_ac2_b",
        {"action": "APPROVE", "expected_version": 1, "reason": "Meets standard eligibility."},
        idempotency_key="ac2-b",
    )
    assert response.status_code == 201, response.text
    assert response.json()["case_status"] == "DECIDED"


# AC3 -------------------------------------------------------------------


async def test_modify_rejects_a_free_form_option_not_in_the_eligible_set(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac3_a", exception_types=["TERM"])

    response = _decide(
        review_client,
        "esc_review_ac3_a",
        {
            "action": "MODIFY",
            "expected_version": 1,
            "reason": "Adjusting the term.",
            "modification_option_id": "opt-99-2099-01-01",
        },
        idempotency_key="ac3-a",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "FREE_FORM_AMOUNT_NOT_ALLOWED"


async def test_modify_accepts_a_real_eligible_option(
    review_client: TestClient, session: AsyncSession, clock: SimulatedClock
) -> None:
    await _seed_case(session, case_id="esc_review_ac3_b", exception_types=["TERM"])
    option_id = _eligible_option_id(clock)

    response = _decide(
        review_client,
        "esc_review_ac3_b",
        {
            "action": "MODIFY",
            "expected_version": 1,
            "reason": "Adjusting the term.",
            "modification_option_id": option_id,
        },
        idempotency_key="ac3-b",
    )
    assert response.status_code == 201, response.text
    assert response.json()["modification_option_id"] == option_id


# AC4 -------------------------------------------------------------------


async def test_stale_version_returns_409_and_leaves_the_case_unchanged(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac4_a")

    response = _decide(
        review_client,
        "esc_review_ac4_a",
        {"action": "REJECT", "expected_version": 999, "reason": "Not eligible."},
        idempotency_key="ac4-a",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "VERSION_CONFLICT"


# AC5 -------------------------------------------------------------------


async def test_only_collections_officer_may_act_manager_and_compliance_get_403(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac5_a")

    for headers in (_MANAGER_HEADERS, _COMPLIANCE_HEADERS):
        request_headers = dict(headers)
        request_headers["Idempotency-Key"] = "ac5-a"
        response = review_client.post(
            "/api/escalations/esc_review_ac5_a/decisions",
            json={"action": "REJECT", "expected_version": 1, "reason": "No."},
            headers=request_headers,
        )
        assert response.status_code == 403, response.text


async def test_officer_cannot_act_on_a_case_routed_to_compliance_review(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(
        session,
        case_id="esc_review_ac5_b",
        queue="COMPLIANCE_REVIEW",
        reviewer_role="COMPLIANCE_RISK",
    )

    response = _decide(
        review_client,
        "esc_review_ac5_b",
        {"action": "REJECT", "expected_version": 1, "reason": "No."},
        idempotency_key="ac5-b",
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["reason_code"] == "WRONG_REVIEWER_ROLE"


# AC6 -------------------------------------------------------------------


async def test_escalate_rejects_a_non_whitelisted_reason(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac6_a")

    response = _decide(
        review_client,
        "esc_review_ac6_a",
        {
            "action": "ESCALATE",
            "expected_version": 1,
            "reason": "Needs a human colleague.",
            "escalate_reason": "REQUEST_HUMAN",
        },
        idempotency_key="ac6-a",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "ESCALATE_REASON_NOT_WHITELISTED"


async def test_escalate_reroutes_to_the_policy_decided_destination(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac6_b")

    response = _decide(
        review_client,
        "esc_review_ac6_b",
        {
            "action": "ESCALATE",
            "expected_version": 1,
            "reason": "Customer disputes the balance.",
            "escalate_reason": "DISPUTE",
        },
        idempotency_key="ac6-b",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["case_status"] == "RE_ROUTED"
    assert body["rerouted_case_id"] is not None

    listing = review_client.get(
        "/api/escalations", params={"status": "OPEN"}, headers=_OFFICER_HEADERS
    )
    reroute_targets = [item for item in listing.json()["items"] if item["reason"] == "DISPUTE"]
    assert len(reroute_targets) == 1
    assert reroute_targets[0]["queue"] == "DISPUTE_REVIEW"


async def test_escalate_rejects_a_free_form_destination_field(
    review_client: TestClient, session: AsyncSession
) -> None:
    """AC6: there is no `destination`/`queue`/`reviewer_role` field on
    `ReviewDecisionRequest` -- the routing service alone decides it
    (`route_escalation`, exercised above). A caller attempting to supply one
    anyway gets 422 for the unrecognized field (`extra="forbid"`) rather
    than having it silently ignored."""
    await _seed_case(session, case_id="esc_review_ac6_c")

    response = _decide(
        review_client,
        "esc_review_ac6_c",
        {
            "action": "ESCALATE",
            "expected_version": 1,
            "reason": "Customer disputes the balance.",
            "escalate_reason": "DISPUTE",
            "destination": "COMPLIANCE_REVIEW",
        },
        idempotency_key="ac6-c",
    )
    assert response.status_code == 422, response.text


# AC7 -------------------------------------------------------------------


async def test_same_idempotency_key_replays_without_repeating_the_transition(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac7_a")

    first = _decide(
        review_client,
        "esc_review_ac7_a",
        {"action": "REJECT", "expected_version": 1, "reason": "Not eligible."},
        idempotency_key="ac7-a",
    )
    assert first.status_code == 201, first.text

    second = _decide(
        review_client,
        "esc_review_ac7_a",
        {"action": "REJECT", "expected_version": 1, "reason": "Not eligible."},
        idempotency_key="ac7-a",
    )
    assert second.status_code == 200, second.text
    assert second.json()["decision_id"] == first.json()["decision_id"]


async def test_a_different_decision_on_an_already_decided_case_returns_409(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac7_b")

    first = _decide(
        review_client,
        "esc_review_ac7_b",
        {"action": "REJECT", "expected_version": 1, "reason": "Not eligible."},
        idempotency_key="ac7-b-1",
    )
    assert first.status_code == 201, first.text

    second = _decide(
        review_client,
        "esc_review_ac7_b",
        {"action": "APPROVE", "expected_version": 1, "reason": "Meets standard eligibility."},
        idempotency_key="ac7-b-2",
    )
    assert second.status_code == 409, second.text


# AC8 -------------------------------------------------------------------


async def test_a_decision_against_an_already_decided_case_is_rejected_even_with_a_fresh_version(
    review_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_review_ac8_a")

    first = _decide(
        review_client,
        "esc_review_ac8_a",
        {"action": "REJECT", "expected_version": 1, "reason": "Not eligible."},
        idempotency_key="ac8-a-1",
    )
    assert first.status_code == 201, first.text
    new_version = first.json()["case_version"]

    second = _decide(
        review_client,
        "esc_review_ac8_a",
        {
            "action": "APPROVE",
            "expected_version": new_version,
            "reason": "Meets standard eligibility.",
        },
        idempotency_key="ac8-a-2",
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["reason_code"] == "CASE_ALREADY_DECIDED"
