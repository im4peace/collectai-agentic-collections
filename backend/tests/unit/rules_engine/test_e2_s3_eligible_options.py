"""Tests for `get_eligible_options` (E2-S3 AC1, AC2, AC4, AC5)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.arrangement import get_eligible_options
from collectai.rules_engine.arrangement._schedule import regular_and_final_installment
from collectai.types.clock import SimulatedClock
from collectai.types.enums import EligibilityClass
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_TODAY = datetime(2026, 10, 19, tzinfo=UTC)


def _active_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


def test_eligible_account_returns_options_summing_exactly_to_overdue_amount() -> None:
    """AC1: worked example from data-models.md's PaymentArrangement entity."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("770.40"),
        dpd=34,
        has_active_ptp=False,
        has_active_arrangement=False,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.ELIGIBLE
    assert [opt.installment_count for opt in result.value.options] == [3, 6, 12]

    three_installment_option = result.value.options[0]
    assert three_installment_option.option_id == "opt-3-2026-10-20"
    assert three_installment_option.installment_amount == Money("256.80")
    assert three_installment_option.final_installment_amount == Money("256.80")
    assert three_installment_option.first_installment_date == date(2026, 10, 20)
    assert three_installment_option.frequency == "MONTHLY"
    assert [entry.due_date for entry in three_installment_option.schedule] == [
        date(2026, 10, 20),
        date(2026, 11, 20),
        date(2026, 12, 20),
    ]

    for option in result.value.options:
        schedule_sum = sum((entry.amount.amount for entry in option.schedule), start=Decimal("0"))
        assert Money(schedule_sum) == Money("770.40")


def test_eligible_options_are_deterministic_across_repeated_calls() -> None:
    """AC1: same inputs, policy version and clock always give the identical list."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    first_call = get_eligible_options(
        provider, clock, Money("770.40"), 34, has_active_ptp=False, has_active_arrangement=False
    )
    second_call = get_eligible_options(
        provider, clock, Money("770.40"), 34, has_active_ptp=False, has_active_arrangement=False
    )

    assert first_call.value == second_call.value


@pytest.mark.parametrize(
    ("total", "count"),
    [
        (Decimal("770.40"), 3),  # divides evenly
        (Decimal("100.03"), 3),  # 1-cent remainder
        (Decimal("1000.01"), 3),  # 2-cent remainder
        (Decimal("999.97"), 6),
        (Decimal("500.00"), 12),
    ],
)
def test_regular_and_final_installment_never_loses_a_cent(total: Decimal, count: int) -> None:
    """AC1 property: the schedule always sums exactly to `total`, for evenly and
    unevenly dividing amounts alike."""
    regular, final = regular_and_final_installment(total, count)

    assert regular * (count - 1) + final == total
    assert final >= Decimal("0")


def test_uneven_division_worked_example_matches_expected_cents() -> None:
    """AC1: a concrete remainder case, spelled out (not just asserted algebraically)."""
    regular, final = regular_and_final_installment(Decimal("1000.01"), 3)

    assert regular == Decimal("333.33")
    assert final == Decimal("333.35")
    assert regular * 2 + final == Decimal("1000.01")


def test_dpd_beyond_eligible_max_returns_not_eligible_with_empty_options() -> None:
    """AC2: DPD beyond the policy limit (policy-v1 eligible_max_dpd=89)."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("500.00"),
        dpd=90,
        has_active_ptp=False,
        has_active_arrangement=False,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.NOT_ELIGIBLE
    assert result.value.options == []
    assert result.value.reason_code == ReasonCode.EXCEEDS_THRESHOLD


def test_overdue_amount_below_minimum_returns_not_eligible_with_empty_options() -> None:
    """AC2: overdue amount below policy-v1's min_overdue_amount=100.00."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("50.00"),
        dpd=10,
        has_active_ptp=False,
        has_active_arrangement=False,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.NOT_ELIGIBLE
    assert result.value.options == []
    assert result.value.reason_code == ReasonCode.BELOW_MIN_AMOUNT


def test_active_arrangement_conflict_blocks_with_amend_or_cancel_permitted_paths() -> None:
    """AC4: an active arrangement conflicts (policy-v1 allow_with_active_ptp=false)."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("500.00"),
        dpd=20,
        has_active_ptp=False,
        has_active_arrangement=True,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.NOT_ELIGIBLE
    assert result.value.options == []
    assert result.value.reason_code == ReasonCode.CONFLICTING_ACTIVE_ITEM
    assert result.value.permitted_paths == ["AMEND", "CANCEL"]


def test_active_ptp_conflict_blocks_with_amend_or_cancel_permitted_paths() -> None:
    """AC4: an active PTP conflicts (policy-v1 allow_with_active_ptp=false)."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("500.00"),
        dpd=20,
        has_active_ptp=True,
        has_active_arrangement=False,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.reason_code == ReasonCode.CONFLICTING_ACTIVE_ITEM
    assert result.value.permitted_paths == ["AMEND", "CANCEL"]


def test_installment_count_below_min_installment_amount_is_excluded_not_a_hard_failure() -> None:
    """A count whose regular installment is below min_installment_amount (25.00)
    is excluded, but the account remains ELIGIBLE with the remaining options."""
    clock = SimulatedClock(_TODAY)
    provider = _active_provider(clock)

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("100.00"),
        dpd=10,
        has_active_ptp=False,
        has_active_arrangement=False,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.ELIGIBLE
    assert [opt.installment_count for opt in result.value.options] == [3]


def test_policy_unavailable_returns_failure_result_with_no_options() -> None:
    """AC5: no active PolicyRuleSet -> a failure result, never a guess."""
    clock = SimulatedClock(_TODAY)
    provider = PolicyProvider()  # never registered/activated

    result = get_eligible_options(
        provider,
        clock,
        overdue_amount=Money("500.00"),
        dpd=10,
        has_active_ptp=False,
        has_active_arrangement=False,
    )

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE
    assert result.failure.details == {"policy_version": None}
