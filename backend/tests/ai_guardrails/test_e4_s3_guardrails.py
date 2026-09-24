"""E4-S3 AC1, AC2, AC3: guardrails applied to next-best-action output,
independent of any database (`bt/ai_guardrails/` convention -- only the LLM
provider boundary is exercised, and here not even that: these guardrails are
pure functions over already-produced structured output).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from collectai.ai_orchestration.grounding import GroundedFacts
from collectai.ai_orchestration.schemas.nba import NbaRecommendationOutput
from collectai.api.schemas.customer360 import (
    AccountBlock,
    AiBlock,
    Customer360,
    DeterministicBlock,
    EscalationBlock,
    Factor,
    PriorityResult,
    ProfileBlock,
    RecordCheck,
    SnapshotInfo,
    TreatmentBlock,
)
from collectai.application._recommendation_governance import requires_human_review
from collectai.application._recommendation_guardrails import (
    apply_guardrails,
    safe_fallback_recommendation,
)
from collectai.types.enums import (
    ContentSource,
    Freshness,
    NbaAction,
    PriorityBand,
    RecommendationStatus,
)
from collectai.types.money import Money

_ALLOWED_FACTOR_IDS = frozenset(
    {"dpd", "overdue_amount", "broken_ptp_count", "recent_contact_outcome"}
)
_FACTS = GroundedFacts(
    currency_amounts=frozenset({"640.00", "3200.00"}), dates=frozenset(), option_ids=frozenset()
)


def _valid_output(
    *, rationale: str = "Contact the customer about the 640.00 overdue amount.",
    referenced_factor_ids: list[str] | None = None,
) -> NbaRecommendationOutput:
    return NbaRecommendationOutput(
        action=NbaAction.CONTACT_CUSTOMER,
        rationale=rationale,
        referenced_factor_ids=referenced_factor_ids or ["overdue_amount"],
    )


def test_schema_rejects_an_action_outside_the_closed_nba_action_set() -> None:
    with pytest.raises(ValidationError):
        NbaRecommendationOutput.model_validate(
            {"action": "OFFER_SETTLEMENT", "rationale": "x", "referenced_factor_ids": []}
        )


def test_schema_rejects_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        NbaRecommendationOutput.model_validate(
            {
                "action": "CONTACT_CUSTOMER",
                "rationale": "x",
                "referenced_factor_ids": [],
                "confidence": "high",
            }
        )


def test_schema_rejects_a_rationale_longer_than_1500_characters() -> None:
    with pytest.raises(ValidationError):
        NbaRecommendationOutput.model_validate(
            {"action": "CONTACT_CUSTOMER", "rationale": "x" * 1501, "referenced_factor_ids": []}
        )


def test_grounded_rationale_with_only_allowed_factor_ids_passes_through_unchanged() -> None:
    output = _valid_output()

    guarded = apply_guardrails(output, allowed_factor_ids=_ALLOWED_FACTOR_IDS, facts=_FACTS)

    assert guarded.action is NbaAction.CONTACT_CUSTOMER
    assert guarded.rationale == output.rationale
    assert guarded.referenced_factor_ids == ["overdue_amount"]
    assert guarded.content_source is ContentSource.MODEL


def test_ac2_a_fabricated_factor_id_is_rejected_and_replaced_by_templated_text() -> None:
    """AC2: a `referenced_factor_ids` entry the deterministic priority
    calculation never returned is not the deterministic services' output --
    the whole rationale is replaced, not just the offending id filtered out."""
    output = _valid_output(referenced_factor_ids=["overdue_amount", "vulnerability_score"])

    guarded = apply_guardrails(output, allowed_factor_ids=_ALLOWED_FACTOR_IDS, facts=_FACTS)

    assert guarded.content_source is ContentSource.TEMPLATE
    assert guarded.referenced_factor_ids == []
    assert guarded.rationale != output.rationale
    assert "vulnerability_score" not in guarded.rationale


def test_ac2_a_fabricated_currency_figure_is_rejected_and_replaced_by_templated_text() -> None:
    """AC2: a rationale citing a currency amount no deterministic service
    returned is replaced, even though every `referenced_factor_ids` entry is
    valid."""
    output = _valid_output(rationale="You can settle today for $50.00.")

    guarded = apply_guardrails(output, allowed_factor_ids=_ALLOWED_FACTOR_IDS, facts=_FACTS)

    assert guarded.content_source is ContentSource.TEMPLATE
    assert guarded.referenced_factor_ids == []
    assert "50.00" not in guarded.rationale


def test_safe_fallback_recommendation_is_a_fixed_escalate_template() -> None:
    """AC1: the safe "human review" recommendation used once the
    orchestrator's schema-validation retry is exhausted."""
    guarded = safe_fallback_recommendation()

    assert guarded.action is NbaAction.ESCALATE_TO_HUMAN_REVIEW
    assert guarded.content_source is ContentSource.TEMPLATE
    assert guarded.referenced_factor_ids == []
    assert guarded.rationale


def _customer360(*, human_treatment: bool) -> Customer360:
    return Customer360(
        account_id="acc_000123",
        generated_at="2026-10-01T09:00:00Z",
        snapshot=SnapshotInfo(
            as_of="2026-10-01T09:00:00Z",
            record_version=1,
            freshness=Freshness.FRESH,
            freshness_reason_code=None,
            max_age_minutes=60,
        ),
        profile=ProfileBlock(
            customer_id="cus_000041",
            display_name="Alex Rivera",
            email="alex.rivera@example.com",
            phone="+971-50-0000000",
            vulnerability_flag=False,
            vulnerability_category=None,
        ),
        account=AccountBlock(
            account_id="acc_000123",
            account_type="CARD",
            product_name="Everyday Card",
            currency="AED",
            opened_on="2024-01-01",
            outstanding_balance=Money("3200.00"),
            overdue_amount=Money("640.00"),
            undisputed_overdue_amount=Money("640.00"),
            dpd=45,
            bucket="DPD_30_59",
            collection_status="IN_PROGRESS",
            product_attributes={},
        ),
        items=[],
        deterministic=DeterministicBlock(
            policy_version="policy-v1",
            status="OK",
            priority=PriorityResult(
                score="12.34",
                band=PriorityBand.HIGH,
                factors=[
                    Factor(
                        factor_id="overdue_amount",
                        attribute="overdue_amount",
                        value="640.00",
                        normalized_value="0.5000",
                        weight="1",
                        contribution="12.34",
                    )
                ],
                policy_version="policy-v1",
            ),
            treatment=TreatmentBlock(
                human_treatment=human_treatment,
                automated_treatment_suppressed=human_treatment,
                suppressions=[],
            ),
            contact_policy=None,
            payable_options=[],
            record_check=RecordCheck(consistent=True, reason_code=None),
        ),
        ai=AiBlock(status=RecommendationStatus.NOT_GENERATED, recommendation=None),
        interactions=[],
        ptp_history=[],
        hardship_cases=[],
        disputes=[],
        escalation=EscalationBlock(badge=None, has_open_case=False, cases=[]),
    )


def test_ac3_human_treatment_true_requires_human_review() -> None:
    """AC3: an active dispute, hardship, open escalation or vulnerable-
    customer flag all collapse to `treatment.human_treatment` (E2-S4's
    `evaluate_suppression`) -- `requires_human_review` trusts that flag
    directly rather than re-deriving it."""
    customer360 = _customer360(human_treatment=True)

    assert requires_human_review(customer360) is True


def test_ac3_human_treatment_false_does_not_require_human_review() -> None:
    customer360 = _customer360(human_treatment=False)

    assert requires_human_review(customer360) is False


def test_recommendation_status_enum_has_no_extra_stored_states() -> None:
    """Learned-rule sanity check: AI_UNAVAILABLE and NOT_GENERATED are
    response-only states (component-map.md); the recommendation table's own
    CHECK constraint only allows GENERATED/SAFE_FALLBACK/HUMAN_REVIEW_ONLY."""
    stored = {
        RecommendationStatus.GENERATED,
        RecommendationStatus.SAFE_FALLBACK,
        RecommendationStatus.HUMAN_REVIEW_ONLY,
    }
    response_only = {RecommendationStatus.AI_UNAVAILABLE, RecommendationStatus.NOT_GENERATED}
    assert stored | response_only == set(RecommendationStatus)
