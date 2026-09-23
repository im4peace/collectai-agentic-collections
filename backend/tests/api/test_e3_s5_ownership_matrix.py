"""E3-S5: customer binding and object-level authorization for `/api/me/*`.

Mounts `api/routers/me.py`'s router onto the shared `api_client` app the
same way `test_e3_s1_rbac_matrix.py`'s `probe_client` and
`test_e9_s1_audit_trail_api.py`'s `audit_client` fixtures do, since
`api/app.py` itself is out of this story's file ownership (the orchestrator
wires the real router in once every Group E story lands).

Two customers, each with exactly one of every customer-owned resource type,
are seeded directly through the ORM (mirroring `conftest.py`'s own
`seeded_customer_id` fixture's pattern) so the AC4 matrix can exercise
own/other-customer/nonexistent for all seven single-resource-by-id
endpoints this story owns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.routers import me as me_router_module
from collectai.audit import queries
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.types.enums import Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_POLICY_VERSION = "policy-v1"


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    """`promise_to_pay.policy_version`, `payment_arrangement.policy_version`
    and `escalation_case.routing_policy_version` FK to `policy_rule_set`
    (migration `0006_system_tables`); mirrors
    `persistence/seed/generator.py`'s `_ensure_seed_policy_rule_set_row`,
    which this test does not import to stay independent of that story's
    seed-data package."""
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES (:version, '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) "
            "ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"version": _POLICY_VERSION, "created_at": _NOW},
    )


@dataclass(frozen=True, slots=True)
class SeededCustomer:
    """One of every customer-owned resource type for one customer."""

    customer_id: str
    account_id: str
    ptp_id: str
    payment_event_id: str
    arrangement_id: str
    hardship_case_id: str
    dispute_id: str
    case_id: str


_RESOURCE_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("account", "/api/me/accounts/{id}", "account_id", "acc_nonexistent0"),
    ("ptp", "/api/me/ptps/{id}", "ptp_id", "ptp_nonexistent0"),
    ("payment_event", "/api/me/payment-events/{id}", "payment_event_id", "pay_nonexistent0"),
    ("arrangement", "/api/me/arrangements/{id}", "arrangement_id", "arr_nonexistent0"),
    ("hardship_case", "/api/me/hardship-cases/{id}", "hardship_case_id", "hsp_nonexistent0"),
    ("dispute", "/api/me/disputes/{id}", "dispute_id", "dsp_nonexistent0"),
    ("escalation", "/api/me/escalations/{id}", "case_id", "esc_nonexistent0"),
)


def _owned_id(customer: SeededCustomer, label: str) -> str:
    return {
        "account": customer.account_id,
        "ptp": customer.ptp_id,
        "payment_event": customer.payment_event_id,
        "arrangement": customer.arrangement_id,
        "hardship_case": customer.hardship_case_id,
        "dispute": customer.dispute_id,
        "escalation": customer.case_id,
    }[label]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _seed_customer(session: AsyncSession, *, suffix: str) -> SeededCustomer:
    customer_id = f"cus_0003{suffix}"
    account_id = f"acc_0003{suffix}"
    ptp_id = f"ptp_0003{suffix}"
    payment_event_id = f"pay_0003{suffix}"
    arrangement_id = f"arr_0003{suffix}"
    hardship_case_id = f"hsp_0003{suffix}"
    dispute_id = f"dsp_0003{suffix}"
    case_id = f"esc_0003{suffix}"

    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name=f"Customer {suffix}",
            email=f"customer.{suffix}@example.com",
            phone="+1-555-0100",
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()  # customer row must exist before FK-referencing rows below
    session.add(
        AccountOrm(
            account_id=account_id,
            customer_id=customer_id,
            account_type="CARD",
            product_name="Everyday Card",
            currency="USD",
            opened_on=_NOW.date(),
            product_attributes={},
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=account_id,
            customer_id=customer_id,
            outstanding_balance=Money("500.00"),
            overdue_amount=Money("100.00"),
            dpd=30,
            bucket="DPD_1_29",
            collection_status="IN_PROGRESS",
            as_of=_NOW,
            record_version=1,
            updated_at=_NOW,
        )
    )
    session.add(
        PromiseToPayOrm(
            ptp_id=ptp_id,
            account_id=account_id,
            customer_id=customer_id,
            item_id=None,
            promised_amount=Money("100.00"),
            promised_date=_NOW.date(),
            status="PENDING",
            cumulative_paid=Money("0.00"),
            interaction_reference=None,
            source="CUSTOMER_CHAT",
            created_by_persona="CUSTOMER",
            created_at=_NOW,
            updated_at=_NOW,
            policy_version="policy-v1",
            version=1,
        )
    )
    session.add(
        PaymentEventOrm(
            payment_event_id=payment_event_id,
            account_id=account_id,
            customer_id=customer_id,
            amount=Money("50.00"),
            outcome="SUCCEEDED",
            source="CUSTOMER_CHAT",
            simulated=True,
            occurred_at=_NOW,
            balance_after=Money("450.00"),
            applied_to_ptp_id=None,
            created_by_persona="CUSTOMER",
        )
    )
    session.add(
        PaymentArrangementOrm(
            arrangement_id=arrangement_id,
            account_id=account_id,
            customer_id=customer_id,
            status="ACTIVE",
            created_via="CUSTOMER_CONFIRMATION",
            exception_case_id=None,
            option_id="opt-3-2026-11-01",
            installment_count=3,
            installment_amount=Money("50.00"),
            final_installment_amount=Money("50.00"),
            total_amount=Money("150.00"),
            first_installment_date=date(2026, 11, 1),
            frequency="MONTHLY",
            schedule=[
                {"sequence": 1, "due_date": "2026-11-01", "amount": "50.00"},
                {"sequence": 2, "due_date": "2026-12-01", "amount": "50.00"},
                {"sequence": 3, "due_date": "2027-01-01", "amount": "50.00"},
            ],
            policy_version="policy-v1",
            created_at=_NOW,
            updated_at=_NOW,
            version=1,
        )
    )
    session.add(
        HardshipCaseOrm(
            hardship_case_id=hardship_case_id,
            account_id=account_id,
            customer_id=customer_id,
            conversation_id=None,
            status="OPEN",
            indicators=[
                {"indicator_type": "JOB_LOSS", "customer_statement": "Lost my job."},
            ],
            escalation_case_id=None,
            created_at=_NOW,
            updated_at=_NOW,
            version=1,
        )
    )
    session.add(
        DisputeOrm(
            dispute_id=dispute_id,
            account_id=account_id,
            customer_id=customer_id,
            item_id=None,
            category="AMOUNT_INCORRECT",
            customer_reason="The amount looks wrong.",
            status="OPEN",
            outcome=None,
            resolution_reason=None,
            conversation_id=None,
            escalation_case_id=None,
            created_at=_NOW,
            updated_at=_NOW,
            version=1,
        )
    )
    session.add(
        EscalationCaseOrm(
            case_id=case_id,
            customer_id=customer_id,
            account_id=account_id,
            conversation_id=None,
            item_id=None,
            reason="FINANCIAL_HARDSHIP",
            queue="HARDSHIP_REVIEW",
            reviewer_role="COLLECTIONS_OFFICER",
            priority="NORMAL",
            status="OPEN",
            source="CUSTOMER",
            summary="Customer reported financial hardship.",
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
            updated_at=_NOW,
            version=1,
        )
    )
    await session.flush()
    return SeededCustomer(
        customer_id=customer_id,
        account_id=account_id,
        ptp_id=ptp_id,
        payment_event_id=payment_event_id,
        arrangement_id=arrangement_id,
        hardship_case_id=hardship_case_id,
        dispute_id=dispute_id,
        case_id=case_id,
    )


@pytest_asyncio.fixture
async def seeded_customers(
    engine: AsyncEngine, clean_db: None
) -> tuple[SeededCustomer, SeededCustomer]:
    """Two customers, each owning one of every resource type: `owner` is the
    customer under test, `other` is the cross-customer target."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _ensure_policy_rule_set_row(session)
        owner = await _seed_customer(session, suffix="01")
        other = await _seed_customer(session, suffix="02")
        await session.commit()
    return owner, other


@pytest.fixture
def me_client(api_client: TestClient) -> TestClient:
    api_client.app.include_router(me_router_module.router)
    return api_client


@pytest.fixture
def owner_headers(
    me_client: TestClient, seeded_customers: tuple[SeededCustomer, SeededCustomer]
) -> dict[str, str]:
    owner, _ = seeded_customers
    response = me_client.post(
        "/api/session",
        json={"persona": Persona.CUSTOMER.value, "customer_id": owner.customer_id},
    )
    assert response.status_code == 201, response.text
    token = response.json()["session_token"]
    return {"X-Persona": Persona.CUSTOMER.value, "X-Demo-Session": token}


# ---------------------------------------------------------------------------
# AC4: ownership matrix -- own / other-customer / nonexistent, for every
# single-resource-by-id endpoint this story owns.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "path_template", "id_field", "_nonexistent_id"), _RESOURCE_CASES)
def test_own_resource_returns_200_with_matching_customer_safe_body(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    label: str,
    path_template: str,
    id_field: str,
    _nonexistent_id: str,
) -> None:
    owner, _ = seeded_customers
    resource_id = _owned_id(owner, label)
    response = me_client.get(path_template.format(id=resource_id), headers=owner_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body[id_field] == resource_id
    assert "customer_id" not in body  # customer-safe: never echoes the ownership column


@pytest.mark.parametrize(("label", "path_template", "id_field", "_nonexistent_id"), _RESOURCE_CASES)
def test_other_customers_resource_returns_404(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    label: str,
    path_template: str,
    id_field: str,
    _nonexistent_id: str,
) -> None:
    owner, other = seeded_customers
    response = me_client.get(
        path_template.format(id=_owned_id(other, label)), headers=owner_headers
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(("label", "path_template", "id_field", "nonexistent_id"), _RESOURCE_CASES)
def test_nonexistent_resource_returns_404(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    label: str,
    path_template: str,
    id_field: str,
    nonexistent_id: str,
) -> None:
    response = me_client.get(path_template.format(id=nonexistent_id), headers=owner_headers)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(("label", "path_template", "id_field", "nonexistent_id"), _RESOURCE_CASES)
def test_cross_customer_and_nonexistent_404_bodies_are_identical(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    label: str,
    path_template: str,
    id_field: str,
    nonexistent_id: str,
) -> None:
    """AC3: no resource information is leaked by a different body shape or
    message between "belongs to someone else" and "does not exist"."""
    owner, other = seeded_customers
    other_response = me_client.get(
        path_template.format(id=_owned_id(other, label)), headers=owner_headers
    )
    nonexistent_response = me_client.get(
        path_template.format(id=nonexistent_id), headers=owner_headers
    )
    assert other_response.status_code == nonexistent_response.status_code == 404
    other_body = other_response.json()
    nonexistent_body = nonexistent_response.json()
    other_body["error"].pop("correlation_id")
    nonexistent_body["error"].pop("correlation_id")
    assert other_body == nonexistent_body


@pytest.mark.asyncio
@pytest.mark.parametrize(("label", "path_template", "id_field", "_nonexistent_id"), _RESOURCE_CASES)
async def test_other_customers_resource_writes_exactly_one_cross_customer_denial_audit_event(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    session: AsyncSession,
    label: str,
    path_template: str,
    id_field: str,
    _nonexistent_id: str,
) -> None:
    """AC5: persona, bound customer_id and endpoint are recorded, but never
    the target resource's contents."""
    owner, other = seeded_customers
    response = me_client.get(
        path_template.format(id=_owned_id(other, label)), headers=owner_headers
    )
    assert response.status_code == 404
    correlation_id = response.headers["X-Correlation-Id"]

    events = await queries.list_by_correlation_id(session, correlation_id)
    denial_events = [
        event for event in events if event.event_type == "CROSS_CUSTOMER_ACCESS_DENIED"
    ]
    assert len(denial_events) == 1
    event = denial_events[0]
    assert event.actor_persona is Persona.CUSTOMER
    assert event.customer_id == owner.customer_id  # the requester, not the resource's owner
    assert event.final_action is not None
    endpoint_prefix = path_template.split("{id}")[0].rstrip("/")
    assert endpoint_prefix in event.final_action
    # No resource content anywhere in the event.
    assert event.resource_id is None
    assert event.resource_type is None
    assert event.ai_output is None
    assert event.rule_results is None
    assert event.account_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("label", "path_template", "id_field", "nonexistent_id"), _RESOURCE_CASES)
async def test_nonexistent_resource_writes_no_cross_customer_denial_audit_event(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
    session: AsyncSession,
    label: str,
    path_template: str,
    id_field: str,
    nonexistent_id: str,
) -> None:
    response = me_client.get(path_template.format(id=nonexistent_id), headers=owner_headers)
    assert response.status_code == 404
    correlation_id = response.headers["X-Correlation-Id"]

    events = await queries.list_by_correlation_id(session, correlation_id)
    denial_events = [
        event for event in events if event.event_type == "CROSS_CUSTOMER_ACCESS_DENIED"
    ]
    assert denial_events == []


# ---------------------------------------------------------------------------
# AC1: client-supplied customer_id is never honored.
# ---------------------------------------------------------------------------


def test_client_supplied_customer_id_query_param_is_ignored(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, other = seeded_customers
    response = me_client.get(
        "/api/me/accounts", params={"customer_id": other.customer_id}, headers=owner_headers
    )
    assert response.status_code == 200
    account_ids = {item["account_id"] for item in response.json()["items"]}
    assert account_ids == {owner.account_id}


# ---------------------------------------------------------------------------
# AC2: list and by-account-list endpoints are scoped, and a by-account-list
# endpoint still ownership-checks the account_id itself first.
# ---------------------------------------------------------------------------


def test_list_my_accounts_returns_only_own_accounts(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get("/api/me/accounts", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert [item["account_id"] for item in body["items"]] == [owner.account_id]
    assert body["page"] == {"limit": 20, "offset": 0, "total": 1}


def test_list_ptps_for_owned_account_returns_only_that_accounts_ptp(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(f"/api/me/accounts/{owner.account_id}/ptps", headers=owner_headers)
    assert response.status_code == 200
    assert [item["ptp_id"] for item in response.json()["items"]] == [owner.ptp_id]


def test_list_ptps_for_other_customers_account_returns_404(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    _, other = seeded_customers
    response = me_client.get(f"/api/me/accounts/{other.account_id}/ptps", headers=owner_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_list_payment_events_for_owned_account_returns_only_that_accounts_event(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(
        f"/api/me/accounts/{owner.account_id}/payment-events", headers=owner_headers
    )
    assert response.status_code == 200
    assert [item["payment_event_id"] for item in response.json()["items"]] == [
        owner.payment_event_id
    ]


def test_list_arrangements_for_owned_account_returns_only_that_accounts_arrangement(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(
        f"/api/me/accounts/{owner.account_id}/arrangements", headers=owner_headers
    )
    assert response.status_code == 200
    assert [item["arrangement_id"] for item in response.json()["items"]] == [owner.arrangement_id]


def test_list_my_escalations_returns_only_own_case(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get("/api/me/escalations", headers=owner_headers)
    assert response.status_code == 200
    assert [item["case_id"] for item in response.json()["items"]] == [owner.case_id]


# ---------------------------------------------------------------------------
# Response-shape spot checks for the richer, derived fields.
# ---------------------------------------------------------------------------


def test_own_ptp_response_includes_derived_remaining_amount(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(f"/api/me/ptps/{owner.ptp_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["remaining_amount"] == "100.00"


def test_own_arrangement_response_includes_full_schedule(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(f"/api/me/arrangements/{owner.arrangement_id}", headers=owner_headers)
    assert response.status_code == 200
    schedule = response.json()["option"]["schedule"]
    assert len(schedule) == 3
    assert schedule[0] == {"sequence": 1, "due_date": "2026-11-01", "amount": "50.00"}


def test_own_hardship_case_response_includes_indicator_types(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(
        f"/api/me/hardship-cases/{owner.hardship_case_id}", headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["indicator_types"] == ["JOB_LOSS"]


def test_own_escalation_response_includes_templated_customer_message_not_internals(
    me_client: TestClient,
    seeded_customers: tuple[SeededCustomer, SeededCustomer],
    owner_headers: dict[str, str],
) -> None:
    owner, _ = seeded_customers
    response = me_client.get(f"/api/me/escalations/{owner.case_id}", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["customer_message"]
    assert "reviewer_role" not in body
    assert "summary" not in body
