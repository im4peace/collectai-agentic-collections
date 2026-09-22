"""E2-S1 AC3: band-cutoff boundary behaviour.

policy-v1 band_cutoffs = [35, 65]: LOW below 35, MEDIUM in [35, 65),
HIGH at and above 65. Each boundary is exercised just below and exactly at
the cut-off, using inputs chosen so the score lands on an exact 2dp value
(no rounding ambiguity).
"""

from __future__ import annotations

from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.priority import PriorityInput, compute_priority
from collectai.types.enums import PriorityBand
from collectai.types.money import Money


def _input_with_overdue_amount(overdue_amount: str, dpd: int) -> PriorityInput:
    return PriorityInput(
        dpd=dpd,
        overdue_amount=Money(overdue_amount),
        broken_ptp_count=0,
        recent_contact_outcome=None,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )


def test_score_just_below_low_medium_cutoff_is_low(
    active_policy_provider: PolicyProvider,
) -> None:
    # dpd=45 -> 20.00 contribution; overdue_amount=2998.00 -> 14.99; total 34.99
    priority_input = _input_with_overdue_amount("2998.00", dpd=45)

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.score == "34.99"
    assert result.value.band == PriorityBand.LOW


def test_score_exactly_at_low_medium_cutoff_is_medium(
    active_policy_provider: PolicyProvider,
) -> None:
    # dpd=45 -> 20.00 contribution; overdue_amount=3000.00 -> 15.00; total 35.00
    priority_input = _input_with_overdue_amount("3000.00", dpd=45)

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.score == "35.00"
    assert result.value.band == PriorityBand.MEDIUM


def test_score_just_below_medium_high_cutoff_is_medium(
    active_policy_provider: PolicyProvider,
) -> None:
    # dpd=90 -> 40.00 contribution; overdue_amount=4998.00 -> 24.99; total 64.99
    priority_input = _input_with_overdue_amount("4998.00", dpd=90)

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.score == "64.99"
    assert result.value.band == PriorityBand.MEDIUM


def test_score_exactly_at_medium_high_cutoff_is_high(
    active_policy_provider: PolicyProvider,
) -> None:
    # dpd=90 -> 40.00 contribution; overdue_amount=5000.00 -> 25.00; total 65.00
    priority_input = _input_with_overdue_amount("5000.00", dpd=90)

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.score == "65.00"
    assert result.value.band == PriorityBand.HIGH
