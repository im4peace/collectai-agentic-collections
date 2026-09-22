"""Structural tests for PolicyParameters/PolicyRuleSet models (E1-S2 AC1, AC4)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from collectai.config.policy.models import (
    ArrangementParameters,
    CollectionsOfficerAuthority,
    ComplianceParameters,
    ContactParameters,
    ExceptionAuthority,
    ExceptionParameters,
    ExceptionThresholds,
    FreshnessParameters,
    PaymentParameters,
    PolicyParameters,
    PolicyRuleSet,
    PriorityNormalization,
    PriorityParameters,
    PriorityWeights,
    PtpParameters,
    RoutingDestination,
    RoutingParameters,
    SuppressionParameters,
    VulnerabilityParameters,
    compute_content_hash,
)
from collectai.types.enums import (
    ContactOutcome,
    EscalationPriority,
    EscalationReason,
    ExceptionType,
    PayableOptionType,
    ReviewerRole,
    ReviewQueue,
    SuppressionScope,
    VulnerabilityCategory,
)
from collectai.types.money import Money


def _build_valid_parameters() -> PolicyParameters:
    routing_table = {
        reason: RoutingDestination(
            queue=ReviewQueue.COLLECTIONS_REVIEW, reviewer_role=ReviewerRole.COLLECTIONS_OFFICER
        )
        for reason in EscalationReason
    }
    priority_by_reason = {reason: EscalationPriority.NORMAL for reason in EscalationReason}
    return PolicyParameters(
        priority=PriorityParameters(
            weights=PriorityWeights(
                dpd=Decimal("40"),
                overdue_amount=Decimal("25"),
                broken_ptp_count=Decimal("20"),
                recent_contact_outcome=Decimal("15"),
            ),
            normalization=PriorityNormalization(
                dpd_days=90, overdue_amount=Money("5000.00"), broken_ptp_count=3
            ),
            contact_outcome_scores={
                ContactOutcome.NO_CONTACT: Decimal("1.0"),
                ContactOutcome.CONTACT_NO_COMMITMENT: Decimal("0.7"),
                ContactOutcome.PTP_MADE: Decimal("0.2"),
                ContactOutcome.PTP_BROKEN: Decimal("0.9"),
                ContactOutcome.PAYMENT_MADE: Decimal("0.0"),
            },
            band_cutoffs=[Decimal("35"), Decimal("65")],
        ),
        ptp=PtpParameters(
            window_days=30,
            min_amount=Money("10.00"),
            qualifying_payment_min_amount=Money("5.00"),
        ),
        payment=PaymentParameters(
            payable_options=[PayableOptionType.OVERDUE_AMOUNT, PayableOptionType.FULL_BALANCE]
        ),
        arrangement=ArrangementParameters(
            eligible_max_dpd=89,
            min_overdue_amount=Money("100.00"),
            installment_counts=[3, 6, 12],
            min_installment_amount=Money("25.00"),
            max_start_delay_days=30,
            allow_with_active_ptp=False,
        ),
        exception=ExceptionParameters(
            thresholds=ExceptionThresholds(
                max_installment_count=24,
                max_start_delay_days=60,
                min_installment_amount=Money("15.00"),
            ),
            authority=ExceptionAuthority(
                collections_officer=CollectionsOfficerAuthority(
                    types=[ExceptionType.TERM, ExceptionType.START_DATE],
                    max_overdue_amount=Money("3000.00"),
                )
            ),
        ),
        contact=ContactParameters(max_attempts=3, period_days=7, min_interval_hours=24),
        freshness=FreshnessParameters(max_snapshot_age_minutes=60),
        suppression=SuppressionParameters(
            dispute_scope=SuppressionScope.ITEM,
            hardship_scope=SuppressionScope.ACCOUNT,
            vulnerable_scope=SuppressionScope.ACCOUNT,
            release="HUMAN_DECISION",
        ),
        vulnerability=VulnerabilityParameters(categories=list(VulnerabilityCategory)),
        routing=RoutingParameters(
            table=routing_table,
            fallback=RoutingDestination(
                queue=ReviewQueue.COLLECTIONS_REVIEW, reviewer_role=ReviewerRole.COLLECTIONS_OFFICER
            ),
            priority_by_reason=priority_by_reason,
            reviewer_escalation_reasons=[EscalationReason.DISPUTE],
            aging_warning_hours={
                EscalationPriority.NORMAL: 48,
                EscalationPriority.ELEVATED: 24,
                EscalationPriority.URGENT: 4,
            },
        ),
        compliance=ComplianceParameters(
            review_outcomes=["CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED"]
        ),
    )


def test_valid_policy_parameters_construct_without_error() -> None:
    parameters = _build_valid_parameters()
    assert parameters.priority.weights.dpd == Decimal("40")


def test_policy_rule_set_holds_version_and_parameters() -> None:
    parameters = _build_valid_parameters()
    rule_set = PolicyRuleSet(
        policy_version="policy-v1",
        parameters=parameters,
        content_hash=compute_content_hash(parameters),
        is_active=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        activated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert rule_set.policy_version == "policy-v1"
    assert rule_set.parameters.ptp.min_amount == Money("10.00")


def test_policy_rule_set_is_frozen() -> None:
    parameters = _build_valid_parameters()
    rule_set = PolicyRuleSet(
        policy_version="policy-v1",
        parameters=parameters,
        content_hash=compute_content_hash(parameters),
        is_active=True,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        activated_at=None,
    )
    with pytest.raises(ValidationError):
        rule_set.is_active = False  # type: ignore[misc]


def test_negative_priority_weight_rejected_at_the_model_level() -> None:
    with pytest.raises(ValidationError):
        PriorityWeights(
            dpd=Decimal("-1"),
            overdue_amount=Decimal("25"),
            broken_ptp_count=Decimal("20"),
            recent_contact_outcome=Decimal("15"),
        )


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ContactParameters(max_attempts=3, period_days=7, min_interval_hours=24, extra_field=1)  # type: ignore[call-arg]


def test_compute_content_hash_is_deterministic_and_sensitive_to_changes() -> None:
    parameters_a = _build_valid_parameters()
    parameters_b = _build_valid_parameters()
    assert compute_content_hash(parameters_a) == compute_content_hash(parameters_b)

    mutated = parameters_a.model_copy(
        update={"ptp": parameters_a.ptp.model_copy(update={"min_amount": Money("11.00")})}
    )
    assert compute_content_hash(mutated) != compute_content_hash(parameters_a)
