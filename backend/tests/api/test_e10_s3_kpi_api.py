"""E10-S3 AC1-AC6: `GET /api/kpis` and `GET /api/kpis/eval-runs`, end to end
against a real, migrated Postgres database. Mirrors `test_e7_s5_compliance_
decision.py`'s fixtures and seeding style.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.api.app import create_app
from collectai.config.settings import Settings
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.eval_case_result import EvalCaseResultOrm
from collectai.persistence.orm.eval_run import EvalRunOrm
from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.types.clock import SimulatedClock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, LlmMode, Persona
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CUSTOMER_ID = "cus_kpi01"
_MANAGER_HEADERS = {"X-Persona": Persona.COLLECTIONS_MANAGER.value}
_OFFICER_HEADERS = {"X-Persona": Persona.COLLECTIONS_OFFICER.value}
_COMPLIANCE_HEADERS = {"X-Persona": Persona.COMPLIANCE_RISK.value}

_DEFERRED_KPI_SUBSTRINGS = (
    "right_party_contact",
    "handling_time",
    "cost_per_collected_account",
)


def _account(account_id: str) -> AccountOrm:
    return AccountOrm(
        account_id=account_id,
        customer_id=_CUSTOMER_ID,
        account_type=AccountType.CARD.value,
        product_name="Everyday Card",
        currency="AED",
        opened_on=_NOW.date(),
        product_attributes={},
        created_at=_NOW,
    )


def _delinquency(account_id: str, *, dpd: int, overdue: str) -> DelinquencyRecordOrm:
    return DelinquencyRecordOrm(
        account_id=account_id,
        customer_id=_CUSTOMER_ID,
        outstanding_balance=Money(overdue),
        overdue_amount=Money(overdue),
        dpd=dpd,
        bucket=Bucket.DPD_1_29.value if dpd else Bucket.CURRENT.value,
        collection_status=CollectionStatus.IN_PROGRESS.value if dpd else CollectionStatus.NEW.value,
        as_of=_NOW,
        record_version=1,
        updated_at=_NOW,
    )


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
async def kpi_dataset(engine: AsyncEngine, clean_db: None) -> None:
    """acc_1/acc_2/acc_4 are delinquent (dpd > 0); acc_3 is current (dpd=0)
    and must be excluded from every delinquent-denominator KPI. See the
    module-level comment block in the test functions below for the
    hand-computed expected values this fixture produces."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await _ensure_policy_rule_set_row(db)
        db.add(
            CustomerOrm(
                customer_id=_CUSTOMER_ID,
                display_name="Amina Khalid",
                email="amina.khalid@example.com",
                phone="+971-50-0000000",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        await db.flush()
        for account_id in ("acc_1", "acc_2", "acc_3", "acc_4"):
            db.add(_account(account_id))
        await db.flush()
        db.add(_delinquency("acc_1", dpd=30, overdue="500.00"))
        db.add(_delinquency("acc_2", dpd=45, overdue="300.00"))
        db.add(_delinquency("acc_3", dpd=0, overdue="0.00"))
        db.add(_delinquency("acc_4", dpd=10, overdue="100.00"))

        db.add(
            PaymentEventOrm(
                payment_event_id="pay_kpi_1",
                account_id="acc_1",
                customer_id=_CUSTOMER_ID,
                amount=Money("200.00"),
                outcome="SUCCEEDED",
                source="DEMO_CONTROL",
                simulated=True,
                occurred_at=_NOW,
                balance_after=Money("300.00"),
                applied_to_ptp_id=None,
                proposal_id=None,
                created_by_persona=Persona.COLLECTIONS_OFFICER.value,
            )
        )
        db.add(
            PaymentEventOrm(
                payment_event_id="pay_kpi_2",
                account_id="acc_2",
                customer_id=_CUSTOMER_ID,
                amount=Money("50.00"),
                outcome="FAILED",
                source="DEMO_CONTROL",
                simulated=True,
                occurred_at=_NOW,
                balance_after=Money("300.00"),
                applied_to_ptp_id=None,
                proposal_id=None,
                created_by_persona=Persona.COLLECTIONS_OFFICER.value,
            )
        )

        for ptp_id, account_id, status in (
            ("ptp_kpi_1", "acc_1", "KEPT"),
            ("ptp_kpi_2", "acc_2", "BROKEN"),
            ("ptp_kpi_3", "acc_3", "PENDING"),
            ("ptp_kpi_4", "acc_4", "KEPT"),
        ):
            db.add(
                PromiseToPayOrm(
                    ptp_id=ptp_id,
                    account_id=account_id,
                    customer_id=_CUSTOMER_ID,
                    item_id=None,
                    promised_amount=Money("100.00"),
                    promised_date=_NOW.date(),
                    status=status,
                    cumulative_paid=Money("0.00"),
                    interaction_reference=None,
                    source="CUSTOMER_CHAT",
                    created_by_persona=Persona.CUSTOMER.value,
                    created_at=_NOW,
                    updated_at=_NOW,
                    kept_at=_NOW if status == "KEPT" else None,
                    broken_at=_NOW if status == "BROKEN" else None,
                    cancelled_at=None,
                    cancel_reason=None,
                    policy_version="policy-v1",
                    version=1,
                )
            )

        db.add(
            EscalationCaseOrm(
                case_id="esc_kpi_1",
                customer_id=_CUSTOMER_ID,
                account_id="acc_1",
                conversation_id=None,
                item_id=None,
                reason="EXCEPTIONAL_ARRANGEMENT",
                queue="COLLECTIONS_EXCEPTION_REVIEW",
                reviewer_role="COLLECTIONS_OFFICER",
                priority="ELEVATED",
                status="OPEN",
                source="AI",
                summary="Open, unreviewed",
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
                version=1,
            )
        )
        db.add(
            EscalationCaseOrm(
                case_id="esc_kpi_2",
                customer_id=_CUSTOMER_ID,
                account_id="acc_2",
                conversation_id=None,
                item_id=None,
                reason="POLICY_EXCEPTION",
                queue="COMPLIANCE_REVIEW",
                reviewer_role="COMPLIANCE_RISK",
                priority="NORMAL",
                status="IN_REVIEW",
                source="AI",
                summary="Reviewed one hour after creation",
                requested_terms=None,
                exception_types=None,
                hardship_case_id=None,
                dispute_id=None,
                recommendation_id=None,
                parent_case_id=None,
                rerouted_to_case_id=None,
                routing_policy_version="policy-v1",
                routing_flags=[],
                first_reviewed_at=_NOW - timedelta(hours=1),
                created_at=_NOW - timedelta(hours=2),
                decided_at=None,
                updated_at=_NOW,
                version=1,
            )
        )

        db.add(
            PaymentArrangementOrm(
                arrangement_id="arr_kpi_1",
                account_id="acc_1",
                customer_id=_CUSTOMER_ID,
                status="ACTIVE",
                created_via="CUSTOMER_CONFIRMATION",
                exception_case_id=None,
                option_id="opt_1",
                installment_count=3,
                installment_amount=Money("100.00"),
                final_installment_amount=Money("100.00"),
                total_amount=Money("300.00"),
                first_installment_date=_NOW.date(),
                frequency="MONTHLY",
                schedule=[],
                policy_version="policy-v1",
                created_at=_NOW,
                updated_at=_NOW,
                version=1,
            )
        )

        db.add(
            RecommendationOrm(
                recommendation_id="rec_kpi_1",
                account_id="acc_1",
                customer_id=_CUSTOMER_ID,
                action="CONTACT_CUSTOMER",
                rationale="Test rationale",
                referenced_factor_ids=[],
                status="GENERATED",
                content_source="MODEL",
                model_id="mock-model",
                prompt_version="p1",
                policy_version="policy-v1",
                record_version=1,
                correlation_id="corr-kpi-1",
                created_at=_NOW,
                audit_event_id="aud_kpi_1",
                officer_decision="ACCEPTED",
                officer_decision_reason=None,
                officer_chosen_action=None,
                decided_by_persona=Persona.COLLECTIONS_OFFICER.value,
                decided_at=_NOW,
            )
        )
        db.add(
            RecommendationOrm(
                recommendation_id="rec_kpi_2",
                account_id="acc_2",
                customer_id=_CUSTOMER_ID,
                action="ESCALATE_TO_HUMAN_REVIEW",
                rationale="Test rationale",
                referenced_factor_ids=[],
                status="GENERATED",
                content_source="MODEL",
                model_id="mock-model",
                prompt_version="p1",
                policy_version="policy-v1",
                record_version=1,
                correlation_id="corr-kpi-2",
                created_at=_NOW,
                audit_event_id="aud_kpi_2",
                officer_decision="OVERRIDDEN",
                officer_decision_reason="Chose a different action.",
                officer_chosen_action="CONTACT_CUSTOMER",
                decided_by_persona=Persona.COLLECTIONS_OFFICER.value,
                decided_at=_NOW,
            )
        )
        db.add(
            RecommendationOrm(
                recommendation_id="rec_kpi_3",
                account_id="acc_4",
                customer_id=_CUSTOMER_ID,
                action="CONTACT_CUSTOMER",
                rationale="Not yet decided",
                referenced_factor_ids=[],
                status="GENERATED",
                content_source="MODEL",
                model_id="mock-model",
                prompt_version="p1",
                policy_version="policy-v1",
                record_version=1,
                correlation_id="corr-kpi-3",
                created_at=_NOW,
                audit_event_id="aud_kpi_3",
                officer_decision=None,
                officer_decision_reason=None,
                officer_chosen_action=None,
                decided_by_persona=None,
                decided_at=None,
            )
        )

        db.add(
            HardshipCaseOrm(
                hardship_case_id="hsp_kpi_1",
                account_id="acc_4",
                customer_id=_CUSTOMER_ID,
                conversation_id=None,
                status="OPEN",
                indicators=["JOB_LOSS"],
                escalation_case_id=None,
                created_at=_NOW,
                decided_at=None,
                updated_at=_NOW,
            )
        )
        db.add(
            DisputeOrm(
                dispute_id="dsp_kpi_1",
                account_id="acc_2",
                customer_id=_CUSTOMER_ID,
                item_id=None,
                category="AMOUNT_INCORRECT",
                customer_reason="Test dispute",
                status="OPEN",
                outcome=None,
                resolution_reason=None,
                conversation_id=None,
                escalation_case_id=None,
                created_at=_NOW,
                resolved_at=None,
                updated_at=_NOW,
            )
        )

        db.add(
            EvalRunOrm(
                eval_run_id="evr_kpi_mock",
                mode="MOCK",
                dataset_version="v1",
                dataset_provenance={},
                model_id=None,
                prompt_version="p1",
                policy_version="policy-v1",
                run_at=_NOW,
                case_count=2,
                intent_accuracy=Decimal("1.0000"),
                metrics={},
                input_tokens=None,
                output_tokens=None,
                estimated_cost_usd=None,
                triggered_by="test",
            )
        )
        await db.flush()
        db.add(
            EvalCaseResultOrm(
                eval_case_result_id="evc_kpi_mock_1",
                eval_run_id="evr_kpi_mock",
                case_id="case_1",
                category="PAY_NOW",
                expected={},
                actual={},
                passed=True,
                critical_policy_violation=False,
            )
        )
        db.add(
            EvalRunOrm(
                eval_run_id="evr_kpi_live",
                mode="LIVE",
                dataset_version="v1",
                dataset_provenance={},
                model_id="claude-x",
                prompt_version="p1",
                policy_version="policy-v1",
                run_at=_NOW,
                case_count=3,
                intent_accuracy=Decimal("0.6667"),
                metrics={},
                input_tokens=100,
                output_tokens=50,
                estimated_cost_usd=Decimal("0.010000"),
                triggered_by="test",
            )
        )
        await db.flush()
        for i, passed in enumerate((True, True, False), start=1):
            db.add(
                EvalCaseResultOrm(
                    eval_case_result_id=f"evc_kpi_live_{i}",
                    eval_run_id="evr_kpi_live",
                    case_id=f"live_case_{i}",
                    category="FINANCIAL_HARDSHIP",
                    expected={},
                    actual={},
                    passed=passed,
                    critical_policy_violation=False,
                )
            )

        await db.commit()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(_NOW)


@pytest.fixture
def kpi_client(
    migrated_schema: str, clock: SimulatedClock, kpi_dataset: None
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


def _kpi_by_id(items: list[dict[str, object]], kpi_id: str) -> dict[str, object]:
    for item in items:
        if item["kpi_id"] == kpi_id:
            return item
    raise AssertionError(f"kpi_id {kpi_id!r} not found among {[i['kpi_id'] for i in items]}")


# AC5 -------------------------------------------------------------------


def test_only_collections_manager_reads_kpis(
    kpi_client: TestClient, session: AsyncSession
) -> None:
    response = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text

    customer_response = kpi_client.post(
        "/api/session", json={"persona": Persona.CUSTOMER.value, "customer_id": _CUSTOMER_ID}
    )
    assert customer_response.status_code == 201, customer_response.text
    customer_headers = {
        "X-Persona": Persona.CUSTOMER.value,
        "X-Demo-Session": customer_response.json()["session_token"],
    }

    for label, headers in (
        ("officer", _OFFICER_HEADERS),
        ("compliance", _COMPLIANCE_HEADERS),
        ("customer", customer_headers),
    ):
        forbidden = kpi_client.get("/api/kpis", headers=headers)
        assert forbidden.status_code == 403, f"{label}: {forbidden.text}"


# AC1, AC2 ----------------------------------------------------------------


def test_business_kpis_are_computed_from_seeded_and_simulated_data(
    kpi_client: TestClient,
) -> None:
    response = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    business = body["business"]

    expected_values = {
        "total_delinquent_accounts": "3",
        "total_overdue_amount": "900.00",
        "recovered_amount": "200.00",
        "recovery_rate": "0.1818",
        "ptp_rate": "1.0000",
        "promise_kept_rate": "0.6667",
    }
    for kpi_id, expected_value in expected_values.items():
        kpi = _kpi_by_id(business, kpi_id)
        assert kpi["value"] == expected_value, f"{kpi_id}: {kpi}"
        assert kpi["data_label"] == "ILLUSTRATIVE"
        assert kpi["owner_persona"]
        assert kpi["definition"]
        assert kpi["formula"]


# AC3 -----------------------------------------------------------------------


def test_operational_kpis_are_computed_from_escalation_and_decision_data(
    kpi_client: TestClient,
) -> None:
    response = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text
    operational = response.json()["operational"]

    expected_values = {
        "escalation_rate": "0.6667",
        "review_queue_size": "2",
        "average_time_to_review_ms": "3600000",
        "human_override_rate": "0.5000",
    }
    for kpi_id, expected_value in expected_values.items():
        kpi = _kpi_by_id(operational, kpi_id)
        assert kpi["value"] == expected_value, f"{kpi_id}: {kpi}"


# AC6 -------------------------------------------------------------------


def test_customer_resolution_and_completeness_kpis(kpi_client: TestClient) -> None:
    response = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text
    operational = response.json()["operational"]

    expected_values = {
        "ptp_breakage_rate": "0.3333",
        "self_service_resolution_rate": "0.3333",
        "arrangement_take_up_rate": "0.3333",
        "hardship_case_count": "1",
        "dispute_case_count": "1",
    }
    for kpi_id, expected_value in expected_values.items():
        kpi = _kpi_by_id(operational, kpi_id)
        assert kpi["value"] == expected_value, f"{kpi_id}: {kpi}"
        assert kpi["definition"]
        assert kpi["formula"]
        assert kpi["data_label"] == "ILLUSTRATIVE"


# AC4 -------------------------------------------------------------------


def test_ai_kpis_are_split_mock_and_live_and_deferred_kpis_are_absent(
    kpi_client: TestClient,
) -> None:
    response = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    ai_quality = body["ai_quality"]

    assert ai_quality["live_run_available"] is True
    assert ai_quality["note"]

    mock_accuracy = _kpi_by_id(ai_quality["mock"], "intent_classification_accuracy")
    assert mock_accuracy["data_label"] == "MOCK"
    assert mock_accuracy["claim_status"] == "OBSERVATION_ONLY"

    live_accuracy = _kpi_by_id(ai_quality["live"], "intent_classification_accuracy")
    assert live_accuracy["data_label"] == "LIVE"
    assert live_accuracy["value"] == "0.6667"
    assert live_accuracy["claim_status"] == "FAIL"  # below the 0.90 LIVE target
    assert live_accuracy["target"] == "0.90"

    live_hardship_recall = _kpi_by_id(
        ai_quality["live"], "sensitive_category_recall_financial_hardship"
    )
    assert live_hardship_recall["value"] == "0.6667"
    assert live_hardship_recall["sample_size"] == 3
    assert live_hardship_recall["claim_status"] == "OBSERVATION_ONLY"  # fewer than 30 cases

    all_items = (*body["business"], *body["operational"], *ai_quality["mock"], *ai_quality["live"])
    all_kpi_ids = [item["kpi_id"] for item in all_items]
    for deferred_substring in _DEFERRED_KPI_SUBSTRINGS:
        assert not any(deferred_substring in kpi_id for kpi_id in all_kpi_ids), deferred_substring


# GET /api/kpis/eval-runs ---------------------------------------------------


def test_eval_runs_endpoint_is_manager_only_and_lists_stored_runs(
    kpi_client: TestClient,
) -> None:
    forbidden = kpi_client.get("/api/kpis/eval-runs", headers=_OFFICER_HEADERS)
    assert forbidden.status_code == 403, forbidden.text

    response = kpi_client.get("/api/kpis/eval-runs", headers=_MANAGER_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page"]["total"] == 2
    assert {item["eval_run_id"] for item in body["items"]} == {"evr_kpi_mock", "evr_kpi_live"}

    live_only = kpi_client.get(
        "/api/kpis/eval-runs", headers=_MANAGER_HEADERS, params={"mode": "LIVE"}
    )
    assert live_only.status_code == 200, live_only.text
    assert [item["eval_run_id"] for item in live_only.json()["items"]] == ["evr_kpi_live"]


# Group K (E10-S5 AC1): the P1 document matches what the API really returns ------


def test_the_kpi_tree_document_lists_exactly_the_kpis_the_api_implements(
    kpi_client: TestClient,
) -> None:
    """`docs/portfolio/kpi-tree.md` must document every `kpi_id` the API
    returns, and must not claim IMPLEMENTED for one it does not. The
    per-category recall KPIs only appear once a run holds that category, so
    the expected set also includes every sensitive category the service
    computes them for."""
    from collectai.domain_services.kpi_service import _SENSITIVE_CATEGORIES

    body = kpi_client.get("/api/kpis", headers=_MANAGER_HEADERS).json()
    api_ids = {
        item["kpi_id"]
        for item in (
            *body["business"],
            *body["operational"],
            *body["ai_quality"]["mock"],
            *body["ai_quality"]["live"],
        )
    }
    computable_ids = api_ids | {
        f"sensitive_category_recall_{category.lower()}" for category in _SENSITIVE_CATEGORIES
    }

    doc = (_REPO_ROOT / "docs" / "portfolio" / "kpi-tree.md").read_text(encoding="utf-8")
    documented_implemented = {
        match.group(1)
        for match in re.finditer(r"^\|.*?\| `([a-z_]+)` \|.*\| IMPLEMENTED \|$", doc, re.MULTILINE)
    }

    assert api_ids <= documented_implemented, api_ids - documented_implemented
    assert documented_implemented == computable_ids
