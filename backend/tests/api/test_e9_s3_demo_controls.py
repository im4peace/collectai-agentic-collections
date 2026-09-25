"""E9-S3 AC1-AC4: `/api/demo-controls/*`, end to end against a real, migrated
Postgres database. Mirrors `test_e7_s4_exceptional_arrangement.py`'s fixture
shape.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.seed.generator import (
    DEFAULT_ACCOUNT_COUNT,
    DEFAULT_RANDOM_SEED,
    generate_seed_dataset,
)
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_850101"
_ACCOUNT_ID = "acc_850201"
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
                display_name="Uma Krishnan",
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
        db_session.add(
            PromiseToPayOrm(
                ptp_id="ptp_850301",
                account_id=_ACCOUNT_ID,
                customer_id=_CUSTOMER_ID,
                item_id=None,
                promised_amount=Money("770.40"),
                promised_date=_NOW.date(),
                status="PENDING",
                cumulative_paid=Money("0.00"),
                interaction_reference=None,
                source="OFFICER_MANUAL",
                created_by_persona="COLLECTIONS_OFFICER",
                created_at=_NOW,
                updated_at=_NOW,
                kept_at=None,
                broken_at=None,
                cancelled_at=None,
                cancel_reason=None,
                policy_version="policy-v1",
                version=1,
            )
        )
        await db_session.commit()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(_NOW)


def _settings(*, demo_controls_enabled: bool, database_url: str) -> Settings:
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
        demo_controls_enabled=demo_controls_enabled,
        database_url=database_url,
    )


@pytest.fixture
def demo_client(
    migrated_schema: str, clock: SimulatedClock, seeded_account: None
) -> Iterator[TestClient]:
    settings = _settings(demo_controls_enabled=True, database_url=migrated_schema)
    app = create_app(settings, clock=clock)
    app.state.settings = settings
    with TestClient(app) as client:
        yield client


@pytest.fixture
def disabled_demo_client(
    migrated_schema: str, clock: SimulatedClock, seeded_account: None
) -> Iterator[TestClient]:
    settings = _settings(demo_controls_enabled=False, database_url=migrated_schema)
    app = create_app(settings, clock=clock)
    app.state.settings = settings
    with TestClient(app) as client:
        yield client


def _post(
    client: TestClient, path: str, body: object, *, idempotency_key: str | None = None
) -> object:
    headers = dict(_OFFICER_HEADERS)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return client.post(f"/api/demo-controls{path}", json=body, headers=headers)


# AC1 -------------------------------------------------------------------


def test_flag_off_returns_404_for_every_route(disabled_demo_client: TestClient) -> None:
    get_response = disabled_demo_client.get(
        "/api/demo-controls/state", headers=_OFFICER_HEADERS
    )
    assert get_response.status_code == 404, get_response.text

    post_response = _post(disabled_demo_client, "/reseed", {"confirm": True})
    assert post_response.status_code == 404, post_response.text


def test_flag_on_shows_mode_as_text(demo_client: TestClient) -> None:
    response = demo_client.get("/api/demo-controls/state", headers=_OFFICER_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["llm_mode"] == "MOCK"
    assert body["demo_controls_enabled"] is True
    assert body["clock"]["mode"] == "SIMULATED"


def test_non_officer_personas_receive_403(demo_client: TestClient) -> None:
    response = demo_client.get(
        "/api/demo-controls/state", headers={"X-Persona": Persona.COLLECTIONS_MANAGER.value}
    )
    assert response.status_code == 403, response.text


# AC2 -------------------------------------------------------------------


async def test_advance_clock_and_breakage_run_marks_due_ptps_broken(
    demo_client: TestClient, session: AsyncSession
) -> None:
    advance_response = _post(demo_client, "/clock/advance", {"days": 5})
    assert advance_response.status_code == 200, advance_response.text
    new_time = datetime.fromisoformat(
        advance_response.json()["clock"]["current_time"].replace("Z", "+00:00")
    )
    assert new_time == _NOW + timedelta(days=5)

    run_response = _post(demo_client, "/ptp-lifecycle/run", None)
    assert run_response.status_code == 200, run_response.text
    body = run_response.json()
    assert body["broken"] == 1
    assert body["evaluated"] == 1

    ptp = await session.get(PromiseToPayOrm, "ptp_850301")
    assert ptp is not None
    assert ptp.status == "BROKEN"


async def test_advance_clock_with_refresh_snapshots_marks_every_record_fresh(
    demo_client: TestClient, session: AsyncSession
) -> None:
    """Group J finding: every seeded `DelinquencyRecord.as_of` is a fixed
    historical constant (`persistence.seed.generator._SEED_NOW`), so it
    reads `Freshness.STALE` (`rules_engine.freshness.check_freshness`) as
    soon as real/demo time has moved more than `policy.parameters.freshness
    .max_snapshot_age_minutes` past it -- blocking every PTP/proposal
    confirm in the app. `refresh_snapshots=true` (the default) fixes this by
    marking every record's snapshot fresh as of the now-advanced clock."""
    before = await session.get(DelinquencyRecordOrm, _ACCOUNT_ID)
    assert before is not None
    assert before.record_version == 1

    advance_response = _post(demo_client, "/clock/advance", {"days": 5, "refresh_snapshots": True})
    assert advance_response.status_code == 200, advance_response.text
    body = advance_response.json()
    assert body["snapshots_refreshed"] == 1

    session.expire_all()
    after = await session.get(DelinquencyRecordOrm, _ACCOUNT_ID)
    assert after is not None
    assert after.record_version == 2
    assert after.as_of == _NOW + timedelta(days=5)
    # dpd/overdue_amount/bucket are never recomputed by this endpoint (no
    # core-sync/DPD recomputation service exists) -- only the snapshot
    # timestamp and version move.
    assert after.dpd == before.dpd
    assert after.overdue_amount == before.overdue_amount


async def test_advance_clock_with_refresh_snapshots_false_leaves_records_untouched(
    demo_client: TestClient, session: AsyncSession
) -> None:
    advance_response = _post(demo_client, "/clock/advance", {"days": 5, "refresh_snapshots": False})
    assert advance_response.status_code == 200, advance_response.text
    assert advance_response.json()["snapshots_refreshed"] == 0

    session.expire_all()
    record = await session.get(DelinquencyRecordOrm, _ACCOUNT_ID)
    assert record is not None
    assert record.record_version == 1
    assert record.as_of == _NOW


# AC3 -------------------------------------------------------------------


async def test_simulate_payment_creates_a_demo_control_payment_event(
    demo_client: TestClient, session: AsyncSession
) -> None:
    response = _post(
        demo_client,
        "/payments/simulate",
        {"account_id": _ACCOUNT_ID, "amount": "100.00"},
        idempotency_key="demo-pay-1",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["payment_event"]["source"] == "DEMO_CONTROL"
    assert body["payment_event"]["simulated"] is True
    assert body["payment_event"]["amount"] == "100.00"

    events = (await session.execute(select(PaymentEventOrm))).scalars().all()
    assert len(events) == 1
    assert events[0].source == "DEMO_CONTROL"
    assert events[0].simulated is True


async def test_simulate_payment_idempotency_key_replay_creates_no_second_event(
    demo_client: TestClient, session: AsyncSession
) -> None:
    body = {"account_id": _ACCOUNT_ID, "amount": "50.00"}
    first = _post(demo_client, "/payments/simulate", body, idempotency_key="demo-pay-2")
    assert first.status_code == 201, first.text

    second = _post(demo_client, "/payments/simulate", body, idempotency_key="demo-pay-2")
    assert second.status_code == 200, second.text
    assert second.json()["replayed"] is True

    events = (await session.execute(select(PaymentEventOrm))).scalars().all()
    assert len(events) == 1


async def test_simulate_payment_zero_amount_is_rejected(
    demo_client: TestClient, session: AsyncSession
) -> None:
    response = _post(
        demo_client,
        "/payments/simulate",
        {"account_id": _ACCOUNT_ID, "amount": "0.00"},
        idempotency_key="demo-pay-3",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["reason_code"] == "ZERO_AMOUNT"


# AC4 -------------------------------------------------------------------


async def test_reseed_restores_a_mutated_seeded_account_and_is_audited(
    demo_client: TestClient, session: AsyncSession
) -> None:
    seed_account_id = "acc_000001"
    seed_customer_id = "cus_000001"
    dataset = generate_seed_dataset(
        account_count=DEFAULT_ACCOUNT_COUNT, random_seed=DEFAULT_RANDOM_SEED
    )
    seed_record = next(
        row for row in dataset.delinquency_records if row["account_id"] == seed_account_id
    )
    seed_customer_row = next(
        row for row in dataset.customers if row["customer_id"] == seed_customer_id
    )

    session.add(
        CustomerOrm(
            customer_id=seed_customer_id,
            display_name="Mutated Name",
            email="mutated@example.com",
            phone="+1-555-0000",
            vulnerability_flag=False,
            vulnerability_category=None,
            created_at=seed_customer_row["created_at"],
            updated_at=seed_customer_row["updated_at"],
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id=seed_account_id,
            customer_id=seed_customer_id,
            account_type=AccountType.CARD.value,
            product_name="Test",
            currency="AED",
            opened_on=_NOW.date(),
            product_attributes={},
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=seed_account_id,
            customer_id=seed_customer_id,
            outstanding_balance=Money("999999.99"),
            overdue_amount=Money("999999.99"),
            dpd=900,
            bucket=Bucket.DPD_90_PLUS.value,
            collection_status=CollectionStatus.IN_PROGRESS.value,
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    await session.commit()

    response = _post(demo_client, "/reseed", {"confirm": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["customers"] >= 1
    assert body["accounts"] >= 1
    assert body["delinquency_records"] >= 1

    restored = await session.get(DelinquencyRecordOrm, seed_account_id)
    assert restored is not None
    assert restored.outstanding_balance == seed_record["outstanding_balance"]
    assert restored.overdue_amount == seed_record["overdue_amount"]
    assert restored.dpd == seed_record["dpd"]

    events = (
        (
            await session.execute(
                select(AuditEventOrm).where(AuditEventOrm.event_type == "DEMO_RESEED")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].actor_persona == "COLLECTIONS_OFFICER"
