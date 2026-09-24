"""E4-S3 AC1-AC5 end to end, against a real migrated Postgres database.

`api/routers/recommendations.py` is not yet wired into `api/app.py` (a
parallel-batch sibling, E6-S1, lands in the same window and touches that
file too -- see the router's own module docstring), so this suite builds its
own minimal `FastAPI` app around it, mirroring `api/app.py::create_app`'s
lifespan exactly, rather than using `conftest.py`'s `api_client` fixture
(which wraps the real `create_app` and does not know about this router yet).
It still reuses every other `tests/api/conftest.py` fixture (`migrated_schema`,
`clock`, `clean_db`, `session`) so this suite runs against the same embedded
Postgres instance and schema every other `tests/api/` test does.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from collectai.ai_orchestration.schemas.nba import NbaRecommendationOutput
from collectai.api.deps import get_audit_service
from collectai.api.middleware.errors import correlation_id_middleware, register_error_handlers
from collectai.api.routers.recommendations import get_llm_provider, get_provider_mode, router
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.config.policy.loader import SEED_POLICY_V1_VERSION, load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import Settings
from collectai.llm_provider.base import ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.persistence.db import build_engine, build_session_factory
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.types.clock import Clock, SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    DisputeCategory,
    DisputeStatus,
    LlmMode,
    NbaAction,
    Persona,
    ProviderMode,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_400301"
_CUSTOMER_ID = "cus_400201"
_DISPUTED_ACCOUNT_ID = "acc_400302"
_DISPUTED_CUSTOMER_ID = "cus_400202"
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}


def _build_app(settings: Settings, clock: Clock) -> FastAPI:
    """Mirrors `api/app.py::create_app`'s lifespan, minus every router this
    story does not own (see module docstring)."""
    policy_provider = PolicyProvider()
    policy_provider.register(load_seed_policy_v1(clock))
    policy_provider.activate(SEED_POLICY_V1_VERSION, clock)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        app.state.session_factory = session_factory
        app.state.clock = clock
        app.state.audit_service = AuditService(clock, session_factory)
        app.state.policy_provider = policy_provider
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.middleware("http")(correlation_id_middleware)
    register_error_handlers(app)
    app.include_router(router)
    return app


def _settings(database_url: str) -> Settings:
    return Settings(
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
        database_url=database_url,
    )


@pytest.fixture
def app(migrated_schema: str, clock: SimulatedClock) -> FastAPI:
    return _build_app(_settings(migrated_schema), clock)


@pytest.fixture
def client(app: FastAPI, clean_db: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _script_provider(app: FastAPI, provider: MockProvider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: provider
    app.dependency_overrides[get_provider_mode] = lambda: ProviderMode.MOCK


def _valid_provider_result(
    *, action: str = "CONTACT_CUSTOMER", rationale: str, referenced_factor_ids: list[str]
) -> ProviderResult:
    output = NbaRecommendationOutput(
        action=NbaAction(action), rationale=rationale, referenced_factor_ids=referenced_factor_ids
    )
    return ProviderResult(content=output.model_dump_json(), model_id="mock-nba-1", latency_ms=42.0)


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-v1', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"created_at": _NOW},
    )


async def _seed_account(
    session: AsyncSession, *, account_id: str, customer_id: str, with_open_dispute: bool
) -> None:
    await _ensure_policy_rule_set_row(session)
    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name="Priya Nakamura",
            email=f"{customer_id}@example.com",
            phone="+971-50-0000001",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id=account_id,
            customer_id=customer_id,
            account_type=AccountType.CARD.value,
            product_name="Everyday Card",
            currency="AED",
            opened_on=_NOW.date(),
            product_attributes={},
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=account_id,
            customer_id=customer_id,
            outstanding_balance=Money("3200.00"),
            overdue_amount=Money("640.00"),
            dpd=45,
            bucket=Bucket.DPD_30_59.value,
            collection_status=CollectionStatus.IN_PROGRESS.value,
            as_of=_NOW,
            record_version=3,
            updated_at=_NOW,
        )
    )
    if with_open_dispute:
        session.add(
            DisputeOrm(
                dispute_id=f"dsp_{account_id[-6:]}",
                account_id=account_id,
                customer_id=customer_id,
                item_id=None,
                category=DisputeCategory.AMOUNT_INCORRECT.value,
                customer_reason="The overdue amount looks wrong.",
                status=DisputeStatus.OPEN.value,
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


@pytest_asyncio.fixture
async def seeded_account(session: AsyncSession, clean_db: None) -> None:
    await _seed_account(
        session, account_id=_ACCOUNT_ID, customer_id=_CUSTOMER_ID, with_open_dispute=False
    )


@pytest_asyncio.fixture
async def seeded_disputed_account(session: AsyncSession, clean_db: None) -> None:
    await _seed_account(
        session,
        account_id=_DISPUTED_ACCOUNT_ID,
        customer_id=_DISPUTED_CUSTOMER_ID,
        with_open_dispute=True,
    )


async def _count_recommendations(engine: AsyncEngine, account_id: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            select(RecommendationOrm).where(RecommendationOrm.account_id == account_id)
        )
        return len(result.all())


# ---------------------------------------------------------------------------
# GET (read-only)
# ---------------------------------------------------------------------------


def test_get_recommendation_is_not_generated_when_none_exists(
    client: TestClient, seeded_account: None
) -> None:
    response = client.get(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_GENERATED"
    assert body["recommendation"] is None


def test_get_recommendation_for_unknown_account_is_404(
    client: TestClient, seeded_account: None
) -> None:
    response = client.get(
        "/api/accounts/acc_does_not_exist/recommendation", headers=_OFFICER_HEADERS
    )
    assert response.status_code == 404


def test_customer_persona_is_forbidden_from_reading_recommendations(
    client: TestClient, seeded_account: None, customer_session_headers: dict[str, str]
) -> None:
    """A CUSTOMER with a valid, authenticated demo session (not just an
    unauthenticated `X-Persona: CUSTOMER` header, which fails 401 before
    authorization is even reached) is still 403 -- `recommendation:read` is
    COLLECTIONS_OFFICER-only."""
    response = client.get(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=customer_session_headers
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST generate: AC1, AC4, single-owner
# ---------------------------------------------------------------------------


def test_generate_with_grounded_valid_output_is_stored_as_generated(
    app: FastAPI, client: TestClient, seeded_account: None, engine: AsyncEngine
) -> None:
    provider = MockProvider(
        [
            _valid_provider_result(
                rationale="Contact the customer about the 640.00 overdue amount.",
                referenced_factor_ids=["overdue_amount"],
            )
        ]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "GENERATED"
    rec = body["recommendation"]
    assert rec["action"] == "CONTACT_CUSTOMER"
    assert rec["content_source"] == "MODEL"
    assert rec["model_id"] == "mock-nba-1"
    assert rec["prompt_version"] == "nba_v1"
    assert rec["policy_version"] == "policy-v1"
    assert rec["referenced_factor_ids"] == ["overdue_amount"]


async def test_generate_creates_exactly_one_recommendation_row(
    app: FastAPI, client: TestClient, seeded_account: None, engine: AsyncEngine
) -> None:
    """Code-gen skill's single-owner rule: one POST call, one row."""
    provider = MockProvider(
        [_valid_provider_result(rationale="Contact the customer.", referenced_factor_ids=[])]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    count = await _count_recommendations(engine, _ACCOUNT_ID)
    assert count == 1


def test_ac1_schema_invalid_output_after_one_retry_is_a_stored_safe_fallback(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    provider = MockProvider(
        [
            ProviderResult(content="not valid json {{{", model_id="mock-nba-1", latency_ms=10.0),
            ProviderResult(content="still not valid", model_id="mock-nba-1", latency_ms=10.0),
        ]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SAFE_FALLBACK"
    assert body["recommendation"]["action"] == "ESCALATE_TO_HUMAN_REVIEW"
    assert body["recommendation"]["content_source"] == "TEMPLATE"
    assert body["recommendation"]["model_id"] is None


def test_ac2_fabricated_factor_id_is_replaced_with_templated_rationale(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    provider = MockProvider(
        [
            _valid_provider_result(
                rationale="Contact the customer about the 640.00 overdue amount.",
                referenced_factor_ids=["overdue_amount", "credit_bureau_score"],
            )
        ]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    rec = response.json()["recommendation"]
    assert rec["status"] == "GENERATED"
    assert rec["content_source"] == "TEMPLATE"
    assert rec["referenced_factor_ids"] == []


def test_ac2_fabricated_currency_amount_is_replaced_with_templated_rationale(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    provider = MockProvider(
        [
            _valid_provider_result(
                rationale="You can settle today for $50.00.", referenced_factor_ids=[]
            )
        ]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)

    assert response.status_code == 200
    rec = response.json()["recommendation"]
    assert rec["content_source"] == "TEMPLATE"
    assert "50.00" not in rec["rationale"]


def test_ac3_open_dispute_forces_escalate_regardless_of_ai_output(
    app: FastAPI, client: TestClient, seeded_disputed_account: None
) -> None:
    """AC3: the AI is scripted to propose something else entirely; the
    account's open dispute must still force ESCALATE_TO_HUMAN_REVIEW."""
    provider = MockProvider(
        [
            _valid_provider_result(
                action="REQUEST_PAYMENT",
                rationale="Request payment now.",
                referenced_factor_ids=[],
            )
        ]
    )
    _script_provider(app, provider)

    response = client.post(
        f"/api/accounts/{_DISPUTED_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "HUMAN_REVIEW_ONLY"
    assert body["recommendation"]["action"] == "ESCALATE_TO_HUMAN_REVIEW"
    assert body["recommendation"]["content_source"] == "TEMPLATE"
    # The AI must never have been called at all (deterministic short-circuit).
    assert provider._calls_made == 0  # noqa: SLF001 - internal test assertion


async def test_ac4_generation_writes_an_audit_event_with_model_and_policy_metadata(
    app: FastAPI, client: TestClient, seeded_account: None, session: AsyncSession
) -> None:
    provider = MockProvider(
        [_valid_provider_result(rationale="Contact the customer.", referenced_factor_ids=[])]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    audit_event_id = response.json()["recommendation"]["audit_event_id"]

    row = (
        await session.execute(
            text(
                "SELECT event_type, model_id, prompt_version, policy_version, ai_output "
                "FROM audit_event WHERE audit_event_id = :id"
            ),
            {"id": audit_event_id},
        )
    ).mappings().one()
    assert row["event_type"] == "RECOMMENDATION_GENERATED"
    assert row["model_id"] == "mock-nba-1"
    assert row["prompt_version"] == "nba_v1"
    assert row["policy_version"] == "policy-v1"
    assert row["ai_output"]["action"] == "CONTACT_CUSTOMER"


async def test_ac4_generation_never_changes_the_delinquency_record(
    app: FastAPI, client: TestClient, seeded_account: None, session: AsyncSession
) -> None:
    provider = MockProvider(
        [_valid_provider_result(rationale="Contact the customer.", referenced_factor_ids=[])]
    )
    _script_provider(app, provider)

    response = client.post(f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS)
    assert response.status_code == 200

    record = (
        await session.execute(
            text(
                "SELECT overdue_amount, dpd, record_version FROM delinquency_record "
                "WHERE account_id = :account_id"
            ),
            {"account_id": _ACCOUNT_ID},
        )
    ).mappings().one()
    assert record["overdue_amount"] == Money("640.00").amount
    assert record["dpd"] == 45
    assert record["record_version"] == 3


async def test_ac5_audit_failure_returns_503_with_no_recommendation_body(
    app: FastAPI, client: TestClient, seeded_account: None, engine: AsyncEngine
) -> None:
    provider = MockProvider(
        [_valid_provider_result(rationale="Contact the customer.", referenced_factor_ids=[])]
    )
    _script_provider(app, provider)

    class _AlwaysFailingAuditService:
        async def record(self, draft: Any) -> str:
            raise AuditUnavailable(event_type=draft.event_type, correlation_id=draft.correlation_id)

        async def record_in(self, session: Any, draft: Any) -> None:
            raise AuditUnavailable(event_type=draft.event_type, correlation_id=draft.correlation_id)

    app.dependency_overrides[get_audit_service] = lambda: _AlwaysFailingAuditService()
    try:
        response = client.post(
            f"/api/accounts/{_ACCOUNT_ID}/recommendation", headers=_OFFICER_HEADERS
        )
    finally:
        del app.dependency_overrides[get_audit_service]

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "AUDIT_UNAVAILABLE"
    assert "recommendation" not in body

    count = await _count_recommendations(engine, _ACCOUNT_ID)
    assert count == 0


# ---------------------------------------------------------------------------
# POST decision
# ---------------------------------------------------------------------------


async def _generate_one(app: FastAPI, client: TestClient, account_id: str) -> dict[str, Any]:
    provider = MockProvider(
        [_valid_provider_result(rationale="Contact the customer.", referenced_factor_ids=[])]
    )
    _script_provider(app, provider)
    response = client.post(f"/api/accounts/{account_id}/recommendation", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    result: dict[str, Any] = response.json()["recommendation"]
    return result


async def test_decision_accept_succeeds_without_a_reason(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)

    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers={**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-accept-1"},
        json={"decision": "ACCEPTED"},
    )

    assert response.status_code == 200
    assert response.json()["officer_decision"] == "ACCEPTED"


async def test_decision_override_without_reason_is_422_reason_required(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)

    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers={**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-override-1"},
        json={"decision": "OVERRIDDEN"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "REASON_REQUIRED"


async def test_decision_override_with_reason_succeeds(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)

    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers={**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-override-2"},
        json={
            "decision": "OVERRIDDEN",
            "reason": "Customer already has an active hardship case.",
            "chosen_action": "REFER_TO_HARDSHIP_WORKFLOW",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["officer_decision"] == "OVERRIDDEN"


async def test_decision_rejects_an_unknown_field(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)

    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers={**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-unknown-1"},
        json={"decision": "ACCEPTED", "confidence": "high"},
    )

    assert response.status_code == 422


async def test_decision_without_idempotency_key_is_422(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)

    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers=_OFFICER_HEADERS,
        json={"decision": "ACCEPTED"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "IDEMPOTENCY_KEY_REQUIRED"


async def test_decision_replays_the_same_response_for_a_repeated_key_and_body(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)
    headers = {**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-replay-1"}
    payload = {"decision": "ACCEPTED"}

    first = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers=headers,
        json=payload,
    )
    second = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


async def test_decision_same_key_with_a_different_body_is_409_conflict(
    app: FastAPI, client: TestClient, seeded_account: None
) -> None:
    rec = await _generate_one(app, client, _ACCOUNT_ID)
    headers = {**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-conflict-1"}

    first = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers=headers,
        json={"decision": "ACCEPTED"},
    )
    second = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/{rec['recommendation_id']}/decision",
        headers=headers,
        json={"decision": "OVERRIDDEN", "reason": "Different request body."},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["reason_code"] == "IDEMPOTENCY_KEY_REUSED"


def test_decision_for_unknown_recommendation_id_is_404(
    client: TestClient, seeded_account: None
) -> None:
    response = client.post(
        f"/api/accounts/{_ACCOUNT_ID}/recommendation/rec_doesnotexist12/decision",
        headers={**_OFFICER_HEADERS, "Idempotency-Key": "decide-key-404"},
        json={"decision": "ACCEPTED"},
    )

    assert response.status_code == 404
