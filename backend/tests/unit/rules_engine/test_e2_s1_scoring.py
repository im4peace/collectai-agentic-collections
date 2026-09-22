"""E2-S1 AC1, AC2: deterministic scoring formula and contribution accounting.

AC1: fixed inputs and policy-v1 return the same score, band and ordered
factor list across repeated calls.
AC2: each factor names its input attribute, value and weighted contribution,
and the contributions sum exactly to the score.
"""

from __future__ import annotations

from decimal import Decimal

from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.priority import PriorityInput, compute_priority
from collectai.types.enums import ContactOutcome, PriorityBand
from collectai.types.money import Money


def _saturating_input() -> PriorityInput:
    """All four factors saturate at 1.0 except contact outcome (0.9)."""
    return PriorityInput(
        dpd=90,
        overdue_amount=Money("5000.00"),
        broken_ptp_count=3,
        recent_contact_outcome=ContactOutcome.PTP_BROKEN,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )


def test_repeated_calls_return_identical_score_band_and_ordered_factors(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = _saturating_input()

    results = [
        compute_priority(priority_input, active_policy_provider) for _ in range(100)
    ]

    assert all(result.ok for result in results)
    first = results[0].value
    assert first is not None
    for result in results[1:]:
        assert result.value == first


def test_score_equals_sum_of_saturated_weighted_contributions(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = _saturating_input()

    result = compute_priority(priority_input, active_policy_provider)

    assert result.ok
    assert result.value is not None
    # dpd: 40 * 1.0 = 40.00; overdue_amount: 25 * 1.0 = 25.00;
    # broken_ptp_count: 20 * 1.0 = 20.00; recent_contact_outcome: 15 * 0.9 = 13.50
    assert result.value.score == "98.50"
    assert result.value.band == PriorityBand.HIGH
    assert result.value.policy_version == "policy-v1"


def test_each_factor_names_attribute_value_and_contribution(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = _saturating_input()

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    factors_by_id = {factor.factor_id: factor for factor in result.value.factors}
    assert factors_by_id["dpd"].attribute == "dpd"
    assert factors_by_id["dpd"].value == "90"
    assert factors_by_id["dpd"].weight == "40"
    assert factors_by_id["dpd"].normalized_value == "1.0000"
    assert factors_by_id["dpd"].contribution == "40.00"

    assert factors_by_id["overdue_amount"].value == "5000.00"
    assert factors_by_id["overdue_amount"].contribution == "25.00"

    assert factors_by_id["broken_ptp_count"].value == "3"
    assert factors_by_id["broken_ptp_count"].contribution == "20.00"

    assert factors_by_id["recent_contact_outcome"].value == "PTP_BROKEN"
    assert factors_by_id["recent_contact_outcome"].normalized_value == "0.9000"
    assert factors_by_id["recent_contact_outcome"].contribution == "13.50"


def test_contributions_sum_exactly_to_the_score_with_repeating_decimals(
    active_policy_provider: PolicyProvider,
) -> None:
    """broken_ptp_count=1 of 3 normalizes to a repeating decimal (1/3); the
    per-factor rounding must still sum exactly to the reported score."""
    priority_input = PriorityInput(
        dpd=30,
        overdue_amount=Money("1234.56"),
        broken_ptp_count=1,
        recent_contact_outcome=ContactOutcome.CONTACT_NO_COMMITMENT,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    contribution_total = sum(
        (Decimal(factor.contribution) for factor in result.value.factors), start=Decimal(0)
    )
    assert contribution_total == Decimal(result.value.score)


def test_recent_contact_outcome_none_contributes_zero(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = PriorityInput(
        dpd=0,
        overdue_amount=Money("0.00"),
        broken_ptp_count=0,
        recent_contact_outcome=None,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    factors_by_id = {factor.factor_id: factor for factor in result.value.factors}
    assert factors_by_id["recent_contact_outcome"].normalized_value == "0.0000"
    assert factors_by_id["recent_contact_outcome"].contribution == "0.00"
    assert result.value.score == "0.00"
    assert result.value.band == PriorityBand.LOW


def test_dpd_and_overdue_amount_beyond_saturation_point_are_capped_at_one(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = PriorityInput(
        dpd=900,
        overdue_amount=Money("50000.00"),
        broken_ptp_count=30,
        recent_contact_outcome=ContactOutcome.NO_CONTACT,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    factors_by_id = {factor.factor_id: factor for factor in result.value.factors}
    assert factors_by_id["dpd"].normalized_value == "1.0000"
    assert factors_by_id["overdue_amount"].normalized_value == "1.0000"
    assert factors_by_id["broken_ptp_count"].normalized_value == "1.0000"
    assert result.value.score == "100.00"


def test_factors_ordered_by_contribution_descending_then_factor_id(
    active_policy_provider: PolicyProvider,
) -> None:
    # dpd -> 40.00 (highest); recent_contact_outcome -> 15.00 (second);
    # broken_ptp_count and overdue_amount both tie at 6.67 (third/fourth),
    # so the tie-break by factor_id must place broken_ptp_count before
    # overdue_amount even though overdue_amount is computed first.
    priority_input = PriorityInput(
        dpd=90,
        overdue_amount=Money("1334.00"),
        broken_ptp_count=1,
        recent_contact_outcome=ContactOutcome.NO_CONTACT,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    ordered_ids = [factor.factor_id for factor in result.value.factors]
    assert ordered_ids == [
        "dpd",
        "recent_contact_outcome",
        "broken_ptp_count",
        "overdue_amount",
    ]
    contributions = [factor.contribution for factor in result.value.factors]
    assert contributions == ["40.00", "15.00", "6.67", "6.67"]
