"""E3-S2 AC1-AC4: `GET /api/portfolio` end to end against a real, migrated
Postgres database.

`api/routers/portfolio.py` is not wired into `api/app.py` yet (the
orchestrator adds every Group E story's router there once all of them have
landed; this story must not edit `app.py` itself), so `portfolio_client`
mounts it onto `conftest.py`'s already-built `api_client.app` for this
module only -- the same technique `tests/api/test_e3_s1_rbac_matrix.py`
uses for its synthetic probe router.

Seed data is inserted directly via ORM rows (`conftest.py`'s own
convention note: "Seed whatever additional accounts/delinquency records/
PTPs/interactions your tests need directly via ORM inserts"). Expected
priority bands/scores are computed with the same `rules_engine.priority`
oracle production code uses, rather than hand-derived numbers, so these
assertions stay correct if `policy-v1.json`'s weights ever change.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.routers.portfolio import get_policy_provider
from collectai.api.routers.portfolio import router as portfolio_router
from collectai.audit import queries
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.priority import PriorityInput, PriorityResult, compute_priority
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    ContactOutcome,
    DisputeCategory,
    DisputeStatus,
    InteractionChannel,
    InteractionDirection,
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}

# Account A: low dpd/overdue, no extras -> low priority.
ACCOUNT_A, CUSTOMER_A = "acc_100301", "cus_100201"
# Account B: mid dpd/overdue, one open dispute (flags human_treatment, does
# not change the score).
ACCOUNT_B, CUSTOMER_B = "acc_100302", "cus_100202"
# Account C: high dpd/overdue, two broken PTPs, a PTP_BROKEN contact outcome
# -> high priority.
ACCOUNT_C, CUSTOMER_C = "acc_100303", "cus_100203"
# Account D: overdue_amount is 0.00 -> never listed (api-contracts.md 3.3).
ACCOUNT_D, CUSTOMER_D = "acc_100304", "cus_100204"
# Account E: overdue_amount (900.00) exceeds outstanding_balance (800.00)
# -> INCONSISTENT_RECORD, excluded and audited.
ACCOUNT_E, CUSTOMER_E = "acc_100305", "cus_100205"


@pytest.fixture
def portfolio_client(api_client: TestClient) -> Iterator[TestClient]:
    api_client.app.include_router(portfolio_router)
    yield api_client


def _priority_for(
    *,
    dpd: int,
    overdue_amount: str,
    broken_ptp_count: int = 0,
    recent_contact_outcome: ContactOutcome | None = None,
    has_active_dispute: bool = False,
) -> PriorityResult:
    """The same deterministic oracle `domain_services.portfolio_service`
    calls in production, used here to derive expected bands/scores instead
    of hand-computing them."""
    clock = SimulatedClock(_NOW)
    policy = load_seed_policy_v1(clock)
    provider = PolicyProvider()
    provider.register(policy)
    provider.activate(policy.policy_version, clock)
    result = compute_priority(
        PriorityInput(
            dpd=dpd,
            overdue_amount=Money(overdue_amount),
            broken_ptp_count=broken_ptp_count,
            recent_contact_outcome=recent_contact_outcome,
            has_active_dispute=has_active_dispute,
            has_active_hardship=False,
            has_open_escalation=False,
        ),
        provider,
    )
    assert result.ok
    assert result.value is not None
    return result.value


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    """`promise_to_pay.policy_version` FKs to `policy_rule_set` (migration
    `0006_system_tables`); mirrors `test_e3_s5_ownership_matrix.py`'s
    `_ensure_policy_rule_set_row`."""
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
async def seeded_portfolio(
    session: AsyncSession, clean_db: None
) -> dict[str, PriorityResult]:
    """Five accounts covering AC1-AC4: three eligible (A, B, C), one with
    `overdue_amount == 0` (D, never listed), one internally inconsistent
    (E, excluded and audited). Returns the expected `PriorityResult` for
    each eligible account, keyed by `account_id`."""
    await _ensure_policy_rule_set_row(session)
    for customer_id, display_name in (
        (CUSTOMER_A, "Naledi Dlamini"),
        (CUSTOMER_B, "Mateus Oliveira"),
        (CUSTOMER_C, "Fatima Al-Sayed"),
        (CUSTOMER_D, "Liam O'Connor"),
        (CUSTOMER_E, "Grace Mensah"),
    ):
        session.add(
            CustomerOrm(
                customer_id=customer_id,
                display_name=display_name,
                email=f"{customer_id}@example.com",
                phone="+1-555-0199",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    await session.flush()

    for account_id, customer_id, account_type in (
        (ACCOUNT_A, CUSTOMER_A, AccountType.CARD),
        (ACCOUNT_B, CUSTOMER_B, AccountType.PERSONAL_LOAN),
        (ACCOUNT_C, CUSTOMER_C, AccountType.CARD),
        (ACCOUNT_D, CUSTOMER_D, AccountType.PERSONAL_LOAN),
        (ACCOUNT_E, CUSTOMER_E, AccountType.CARD),
    ):
        session.add(
            AccountOrm(
                account_id=account_id,
                customer_id=customer_id,
                account_type=account_type.value,
                product_name="Everyday Account",
                currency="AED",
                opened_on=_NOW.date(),
                product_attributes={},
                created_at=_NOW,
            )
        )
    await session.flush()

    session.add_all(
        [
            DelinquencyRecordOrm(
                account_id=ACCOUNT_A,
                customer_id=CUSTOMER_A,
                outstanding_balance=Money("2000.00"),
                overdue_amount=Money("200.00"),
                dpd=10,
                bucket=Bucket.DPD_1_29.value,
                collection_status=CollectionStatus.NEW.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            ),
            DelinquencyRecordOrm(
                account_id=ACCOUNT_B,
                customer_id=CUSTOMER_B,
                outstanding_balance=Money("8420.10"),
                overdue_amount=Money("770.40"),
                dpd=45,
                bucket=Bucket.DPD_30_59.value,
                collection_status=CollectionStatus.IN_PROGRESS.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            ),
            DelinquencyRecordOrm(
                account_id=ACCOUNT_C,
                customer_id=CUSTOMER_C,
                outstanding_balance=Money("3200.00"),
                overdue_amount=Money("3200.00"),
                dpd=95,
                bucket=Bucket.DPD_90_PLUS.value,
                collection_status=CollectionStatus.ESCALATED.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            ),
            DelinquencyRecordOrm(
                account_id=ACCOUNT_D,
                customer_id=CUSTOMER_D,
                outstanding_balance=Money("500.00"),
                overdue_amount=Money("0.00"),
                dpd=0,
                bucket=Bucket.CURRENT.value,
                collection_status=CollectionStatus.NEW.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            ),
            DelinquencyRecordOrm(
                account_id=ACCOUNT_E,
                customer_id=CUSTOMER_E,
                outstanding_balance=Money("800.00"),
                overdue_amount=Money("900.00"),
                dpd=40,
                bucket=Bucket.DPD_30_59.value,
                collection_status=CollectionStatus.IN_PROGRESS.value,
                as_of=_NOW,
                record_version=1,
                updated_at=_NOW,
            ),
            PromiseToPayOrm(
                ptp_id="ptp_100401",
                account_id=ACCOUNT_C,
                customer_id=CUSTOMER_C,
                item_id=None,
                promised_amount=Money("300.00"),
                promised_date=_NOW.date(),
                status=PtpStatus.BROKEN.value,
                cumulative_paid=Money("0.00"),
                interaction_reference=None,
                source=PtpSource.OFFICER_MANUAL.value,
                created_by_persona=Persona.COLLECTIONS_OFFICER.value,
                created_at=_NOW,
                updated_at=_NOW,
                kept_at=None,
                broken_at=_NOW,
                cancelled_at=None,
                cancel_reason=None,
                policy_version="policy-v1",
                version=1,
            ),
            PromiseToPayOrm(
                ptp_id="ptp_100402",
                account_id=ACCOUNT_C,
                customer_id=CUSTOMER_C,
                item_id=None,
                promised_amount=Money("150.00"),
                promised_date=_NOW.date(),
                status=PtpStatus.BROKEN.value,
                cumulative_paid=Money("0.00"),
                interaction_reference=None,
                source=PtpSource.OFFICER_MANUAL.value,
                created_by_persona=Persona.COLLECTIONS_OFFICER.value,
                created_at=_NOW,
                updated_at=_NOW,
                kept_at=None,
                broken_at=_NOW,
                cancelled_at=None,
                cancel_reason=None,
                policy_version="policy-v1",
                version=1,
            ),
            InteractionOrm(
                interaction_id="int_100501",
                account_id=ACCOUNT_C,
                customer_id=CUSTOMER_C,
                channel=InteractionChannel.SIMULATED_OUTBOUND_CALL.value,
                direction=InteractionDirection.OUTBOUND.value,
                outcome=ContactOutcome.PTP_BROKEN.value,
                occurred_at=_NOW,
                summary="Simulated outbound call; promise broken.",
                counts_as_attempt=True,
                conversation_id=None,
            ),
            DisputeOrm(
                dispute_id="dsp_100601",
                account_id=ACCOUNT_B,
                customer_id=CUSTOMER_B,
                item_id=None,
                category=DisputeCategory.AMOUNT_INCORRECT.value,
                customer_reason="The statement amount looks wrong to me.",
                status=DisputeStatus.OPEN.value,
                outcome=None,
                resolution_reason=None,
                conversation_id=None,
                escalation_case_id=None,
                created_at=_NOW,
                resolved_at=None,
                updated_at=_NOW,
                version=1,
            ),
        ]
    )
    await session.commit()

    return {
        ACCOUNT_A: _priority_for(dpd=10, overdue_amount="200.00"),
        ACCOUNT_B: _priority_for(dpd=45, overdue_amount="770.40", has_active_dispute=True),
        ACCOUNT_C: _priority_for(
            dpd=95,
            overdue_amount="3200.00",
            broken_ptp_count=2,
            recent_contact_outcome=ContactOutcome.PTP_BROKEN,
        ),
    }


def test_get_portfolio_returns_ac1_fields_for_every_eligible_account(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    response = portfolio_client.get("/api/portfolio", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    body = response.json()

    account_ids = [item["account_id"] for item in body["items"]]
    assert set(account_ids) == {ACCOUNT_A, ACCOUNT_B, ACCOUNT_C}
    assert ACCOUNT_D not in account_ids, "overdue_amount == 0 must never be listed"
    assert ACCOUNT_E not in account_ids, "an inconsistent record must never be listed"

    by_id = {item["account_id"]: item for item in body["items"]}
    item_a = by_id[ACCOUNT_A]
    expected_a = seeded_portfolio[ACCOUNT_A]
    assert item_a["customer_id"] == CUSTOMER_A
    assert item_a["customer_name"] == "Naledi Dlamini"
    assert item_a["account_type"] == "CARD"
    assert item_a["outstanding_balance"] == "2000.00"
    assert item_a["overdue_amount"] == "200.00"
    assert item_a["dpd"] == 10
    assert item_a["bucket"] == "DPD_1_29"
    assert item_a["collection_status"] == "NEW"
    assert item_a["priority_band"] == expected_a.band.value
    assert item_a["priority_score"] == expected_a.score
    assert item_a["human_treatment"] is False
    assert item_a["record_version"] == 1

    item_b = by_id[ACCOUNT_B]
    assert item_b["human_treatment"] is True, "an open dispute must set human_treatment"

    assert body["page"] == {"limit": 50, "offset": 0, "total": 3}
    assert body["policy_version"] == "policy-v1"


def test_get_portfolio_filters_by_dpd_range_and_status_intersect(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    """AC2: dpd_min/dpd_max exclude A (dpd 10); combined with `status` the
    two filters intersect (AND), excluding C (ESCALATED) too."""
    response = portfolio_client.get(
        "/api/portfolio",
        params={"dpd_min": 20, "dpd_max": 100, "status": "IN_PROGRESS"},
        headers=_OFFICER_HEADERS,
    )
    assert response.status_code == 200
    assert [item["account_id"] for item in response.json()["items"]] == [ACCOUNT_B]


def test_get_portfolio_filters_by_priority_band(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    """AC2: `priority_band` is a computed value, filtered post-scoring."""
    band_c = seeded_portfolio[ACCOUNT_C].band
    assert band_c != seeded_portfolio[ACCOUNT_A].band
    assert band_c != seeded_portfolio[ACCOUNT_B].band

    response = portfolio_client.get(
        "/api/portfolio", params={"priority_band": band_c.value}, headers=_OFFICER_HEADERS
    )
    assert response.status_code == 200
    assert [item["account_id"] for item in response.json()["items"]] == [ACCOUNT_C]


def test_get_portfolio_sorts_by_overdue_amount_ascending_and_descending(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    ascending = portfolio_client.get(
        "/api/portfolio",
        params={"sort_by": "overdue_amount", "sort_dir": "asc"},
        headers=_OFFICER_HEADERS,
    )
    descending = portfolio_client.get(
        "/api/portfolio",
        params={"sort_by": "overdue_amount", "sort_dir": "desc"},
        headers=_OFFICER_HEADERS,
    )

    assert [item["account_id"] for item in ascending.json()["items"]] == [
        ACCOUNT_A,
        ACCOUNT_B,
        ACCOUNT_C,
    ]
    assert [item["account_id"] for item in descending.json()["items"]] == [
        ACCOUNT_C,
        ACCOUNT_B,
        ACCOUNT_A,
    ]


def test_get_portfolio_sorts_by_dpd_ascending_and_descending(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    ascending = portfolio_client.get(
        "/api/portfolio", params={"sort_by": "dpd", "sort_dir": "asc"}, headers=_OFFICER_HEADERS
    )
    descending = portfolio_client.get(
        "/api/portfolio", params={"sort_by": "dpd", "sort_dir": "desc"}, headers=_OFFICER_HEADERS
    )

    assert [item["account_id"] for item in ascending.json()["items"]] == [
        ACCOUNT_A,
        ACCOUNT_B,
        ACCOUNT_C,
    ]
    assert [item["account_id"] for item in descending.json()["items"]] == [
        ACCOUNT_C,
        ACCOUNT_B,
        ACCOUNT_A,
    ]


def test_get_portfolio_defaults_to_priority_score_descending(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    expected_order = [
        account_id
        for account_id, _ in sorted(
            seeded_portfolio.items(), key=lambda kv: Decimal(kv[1].score), reverse=True
        )
    ]

    response = portfolio_client.get("/api/portfolio", headers=_OFFICER_HEADERS)

    assert [item["account_id"] for item in response.json()["items"]] == expected_order


def test_get_portfolio_pagination_returns_the_pre_pagination_total(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    response = portfolio_client.get(
        "/api/portfolio",
        params={"limit": 1, "offset": 1, "sort_by": "dpd", "sort_dir": "asc"},
        headers=_OFFICER_HEADERS,
    )
    body = response.json()

    assert body["page"] == {"limit": 1, "offset": 1, "total": 3}
    assert [item["account_id"] for item in body["items"]] == [ACCOUNT_B]


def test_get_portfolio_rejects_dpd_max_below_dpd_min(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    response = portfolio_client.get(
        "/api/portfolio", params={"dpd_min": 50, "dpd_max": 10}, headers=_OFFICER_HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_portfolio_allowed_for_collections_officer(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    """AC4."""
    response = portfolio_client.get("/api/portfolio", headers=_OFFICER_HEADERS)
    assert response.status_code == 200


@pytest.mark.parametrize("persona", [Persona.COLLECTIONS_MANAGER, Persona.COMPLIANCE_RISK])
def test_get_portfolio_forbidden_for_other_staff_personas(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult], persona: Persona
) -> None:
    """AC4."""
    response = portfolio_client.get("/api/portfolio", headers={"X-Persona": persona.value})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_portfolio_forbidden_for_customer(
    portfolio_client: TestClient,
    seeded_portfolio: dict[str, PriorityResult],
    customer_session_headers: dict[str, str],
) -> None:
    """AC4."""
    response = portfolio_client.get("/api/portfolio", headers=customer_session_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_portfolio_returns_503_when_no_active_policy(
    portfolio_client: TestClient, seeded_portfolio: dict[str, PriorityResult]
) -> None:
    """AC1/api-contracts.md 3.3: no active PolicyRuleSet -> fail closed,
    never a partial/unscored page."""
    portfolio_client.app.dependency_overrides[get_policy_provider] = PolicyProvider
    try:
        response = portfolio_client.get("/api/portfolio", headers=_OFFICER_HEADERS)
    finally:
        del portfolio_client.app.dependency_overrides[get_policy_provider]

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "POLICY_UNAVAILABLE"


async def test_inconsistent_record_is_excluded_and_the_count_is_audited(
    portfolio_client: TestClient,
    seeded_portfolio: dict[str, PriorityResult],
    session: AsyncSession,
) -> None:
    """api-contracts.md 3.3: "Accounts with INCONSISTENT_RECORD are
    excluded and counted in the audit log, never scored."""
    response = portfolio_client.get("/api/portfolio", headers=_OFFICER_HEADERS)
    assert response.status_code == 200
    assert ACCOUNT_E not in [item["account_id"] for item in response.json()["items"]]

    correlation_id = response.headers["X-Correlation-Id"]
    events = await queries.list_by_correlation_id(session, correlation_id)
    excluded_events = [
        event
        for event in events
        if event.event_type == "PORTFOLIO_INCONSISTENT_RECORDS_EXCLUDED"
    ]
    assert len(excluded_events) == 1
    assert excluded_events[0].rule_results == {"excluded_count": 1}
