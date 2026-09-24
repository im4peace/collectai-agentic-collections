"""E7-S5 AC1-AC6: `POST /api/escalations/{case_id}/compliance-decision`, end
to end against a real, migrated Postgres database. Mirrors
`test_e7_s2_review_decisions_api.py`'s fixtures and `_seed_case` helper.
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
from collectai.audit.service import AuditService
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import Settings
from collectai.domain_services.escalation_service import create_escalation
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CaseSource,
    CollectionStatus,
    LlmMode,
    Persona,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_830101"
_ACCOUNT_ID = "acc_830201"
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
    queue: str = "COMPLIANCE_REVIEW",
    reviewer_role: str = "COMPLIANCE_RISK",
    status: str = "OPEN",
    version: int = 1,
) -> None:
    session.add(
        EscalationCaseOrm(
            case_id=case_id,
            customer_id=_CUSTOMER_ID,
            account_id=_ACCOUNT_ID,
            conversation_id=None,
            item_id=None,
            reason="POLICY_EXCEPTION",
            queue=queue,
            reviewer_role=reviewer_role,
            priority="ELEVATED",
            status=status,
            source="AI",
            summary="Test compliance case",
            requested_terms=None,
            exception_types=None,
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
                display_name="Sofia Marchetti",
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
def compliance_client(
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
def customer_headers(compliance_client: TestClient) -> dict[str, str]:
    response = compliance_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


def _decide_compliance(
    client: TestClient,
    case_id: str,
    body: dict[str, object],
    *,
    idempotency_key: str,
    headers: dict[str, str] | None = None,
) -> object:
    request_headers = dict(headers or _COMPLIANCE_HEADERS)
    request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/escalations/{case_id}/compliance-decision", json=body, headers=request_headers
    )


# AC1 -------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["POLICY_EXCEPTION", "HIGH_RISK_COMPLIANCE"])
async def test_ai_proposed_escalation_routes_to_compliance_review(
    session: AsyncSession, seeded_account: None, clock: SimulatedClock, reason: str
) -> None:
    """AC1's "proposed by the AI" half: `create_escalation` (the one write
    path any AI-proposed escalation goes through, `source=CaseSource.AI`) is
    reason-generic -- routing to COMPLIANCE_REVIEW/COMPLIANCE_RISK comes only
    from `rules_engine.routing.route_escalation`'s own policy-table lookup,
    never a special case in this module."""
    from collectai.types.enums import EscalationReason

    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    audit_service = AuditService(clock, async_sessionmaker(session.bind, expire_on_commit=False))

    result = await create_escalation(
        session,
        reason=EscalationReason(reason),
        customer_id=_CUSTOMER_ID,
        account_id=_ACCOUNT_ID,
        conversation_id=None,
        item_id=None,
        source=CaseSource.AI,
        policy_provider=provider,
        clock=clock,
        audit_service=audit_service,
        correlation_id=f"corr-ac1-{reason}",
    )
    await session.commit()
    assert result.case.queue == "COMPLIANCE_REVIEW"
    assert result.case.reviewer_role == "COMPLIANCE_RISK"


async def test_reviewer_escalate_to_policy_exception_routes_to_compliance_review(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    """AC1's "raised by a reviewer ESCALATE" half."""
    await _seed_case(
        session,
        case_id="esc_ac1_reviewer",
        queue="COLLECTIONS_REVIEW",
        reviewer_role="COLLECTIONS_OFFICER",
    )
    headers = dict(_OFFICER_HEADERS)
    headers["Idempotency-Key"] = "ac1-reviewer"
    response = compliance_client.post(
        "/api/escalations/esc_ac1_reviewer/decisions",
        json={
            "action": "ESCALATE",
            "expected_version": 1,
            "reason": "Needs compliance review.",
            "escalate_reason": "POLICY_EXCEPTION",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    rerouted_case_id = response.json()["rerouted_case_id"]
    assert rerouted_case_id is not None
    rerouted = await session.get(EscalationCaseOrm, rerouted_case_id)
    assert rerouted is not None
    assert rerouted.queue == "COMPLIANCE_REVIEW"
    assert rerouted.reviewer_role == "COMPLIANCE_RISK"


# AC2 -------------------------------------------------------------------


async def test_compliance_risk_records_a_decision_on_a_compliance_review_case(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_ac2_a")

    response = _decide_compliance(
        compliance_client,
        "esc_ac2_a",
        {"outcome": "CLEARED", "reason": "No compliance concern found.", "expected_version": 1},
        idempotency_key="ac2-a",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["case_id"] == "esc_ac2_a"
    assert body["compliance_outcome"] == "CLEARED"
    assert body["reason"] == "No compliance concern found."
    assert body["reviewer_persona"] == "COMPLIANCE_RISK"
    assert body["decided_at"] is not None
    assert body["case_status"] == "DECIDED"

    case = await session.get(EscalationCaseOrm, "esc_ac2_a")
    assert case is not None
    assert case.status == "DECIDED"
    assert case.version == 2


async def test_compliance_decision_requires_a_reason(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_ac2_b")

    response = _decide_compliance(
        compliance_client,
        "esc_ac2_b",
        {"outcome": "NOT_CLEARED", "reason": "", "expected_version": 1},
        idempotency_key="ac2-b",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


# AC3 -------------------------------------------------------------------


async def test_a_case_outside_compliance_review_is_refused(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(
        session,
        case_id="esc_ac3_a",
        queue="COLLECTIONS_REVIEW",
        reviewer_role="COLLECTIONS_OFFICER",
    )

    response = _decide_compliance(
        compliance_client,
        "esc_ac3_a",
        {"outcome": "CLEARED", "reason": "Reviewed.", "expected_version": 1},
        idempotency_key="ac3-a",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "WRONG_QUEUE"


async def test_an_already_decided_case_is_refused(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_ac3_b", status="DECIDED")

    response = _decide_compliance(
        compliance_client,
        "esc_ac3_b",
        {"outcome": "CLEARED", "reason": "Reviewed.", "expected_version": 1},
        idempotency_key="ac3-b",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["reason_code"] == "INVALID_STATE_TRANSITION"


# AC4 -------------------------------------------------------------------


async def _financial_snapshot(session: AsyncSession) -> tuple[object, ...]:
    delinquency = (await session.execute(select(DelinquencyRecordOrm))).scalars().all()
    arrangements = (await session.execute(select(PaymentArrangementOrm))).scalars().all()
    ptps = (await session.execute(select(PromiseToPayOrm))).scalars().all()
    payments = (await session.execute(select(PaymentEventOrm))).scalars().all()
    return (
        [
            (r.account_id, str(r.outstanding_balance), str(r.overdue_amount), r.record_version)
            for r in delinquency
        ],
        [(a.arrangement_id, a.status, a.version) for a in arrangements],
        [(p.ptp_id, p.status, p.updated_at) for p in ptps],
        [(p.payment_event_id,) for p in payments],
    )


async def test_compliance_decision_touches_no_financial_table(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    """AC4: a before-and-after comparison of the financial tables around a
    compliance decision -- `compliance_service` imports none of
    `arrangement_service`/`ptp_service`/`payment_service`/`hardship_service`,
    so there is no code path by which it could write to any of them."""
    await _seed_case(session, case_id="esc_ac4_a")
    before = await _financial_snapshot(session)

    response = _decide_compliance(
        compliance_client,
        "esc_ac4_a",
        {"outcome": "REMEDIATION_REQUIRED", "reason": "Needs follow-up.", "expected_version": 1},
        idempotency_key="ac4-a",
    )
    assert response.status_code == 201, response.text

    after = await _financial_snapshot(session)
    assert before == after


# AC5 -------------------------------------------------------------------


async def test_compliance_decision_is_audited(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_ac5_a")

    response = _decide_compliance(
        compliance_client,
        "esc_ac5_a",
        {"outcome": "CLEARED", "reason": "Reviewed and cleared.", "expected_version": 1},
        idempotency_key="ac5-a",
    )
    assert response.status_code == 201, response.text
    decision_id = response.json()["decision_id"]

    events = (
        (
            await session.execute(
                select(AuditEventOrm).where(
                    AuditEventOrm.event_type == "COMPLIANCE_DECISION_RECORDED",
                    AuditEventOrm.resource_id == decision_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


async def test_compliance_decision_idempotency_key_replay_does_not_repeat_the_transition(
    compliance_client: TestClient, session: AsyncSession
) -> None:
    await _seed_case(session, case_id="esc_ac5_b")

    body = {"outcome": "CLEARED", "reason": "Reviewed and cleared.", "expected_version": 1}
    first = _decide_compliance(compliance_client, "esc_ac5_b", body, idempotency_key="ac5-b")
    assert first.status_code == 201, first.text

    second = _decide_compliance(compliance_client, "esc_ac5_b", body, idempotency_key="ac5-b")
    assert second.status_code == 200, second.text
    assert second.json()["replayed"] is True
    assert second.json()["decision_id"] == first.json()["decision_id"]

    case = await session.get(EscalationCaseOrm, "esc_ac5_b")
    assert case is not None
    assert case.version == 2  # not bumped a second time by the replay


# AC6 -------------------------------------------------------------------


async def test_officer_manager_and_customer_receive_403(
    compliance_client: TestClient, session: AsyncSession, customer_headers: dict[str, str]
) -> None:
    await _seed_case(session, case_id="esc_ac6_a")
    body = {"outcome": "CLEARED", "reason": "Reviewed.", "expected_version": 1}

    for label, headers in (
        ("officer", _OFFICER_HEADERS),
        ("manager", _MANAGER_HEADERS),
        ("customer", customer_headers),
    ):
        response = _decide_compliance(
            compliance_client, "esc_ac6_a", body, idempotency_key=f"ac6-{label}", headers=headers
        )
        assert response.status_code == 403, f"{label}: {response.text}"
