"""Tests for PTP amount and date validation (E2-S2 AC1, AC2, AC3)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import SimulatedClock
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_ACTIVATION_INSTANT = datetime(2026, 9, 1, tzinfo=UTC)
_TODAY = date(2026, 9, 1)
_OVERDUE_AMOUNT = Money("900.00")


def _provider_with_active_seed_policy(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


def _input(**overrides: object) -> PtpValidationInput:
    fields: dict[str, object] = {
        "promised_amount": "250.00",
        "promised_date": _TODAY + timedelta(days=10),
        "overdue_amount": _OVERDUE_AMOUNT,
    }
    fields.update(overrides)
    return PtpValidationInput(**fields)  # type: ignore[arg-type]


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(_ACTIVATION_INSTANT)


@pytest.fixture
def provider(clock: SimulatedClock) -> PolicyProvider:
    return _provider_with_active_seed_policy(clock)


# --- AC1: amount checks ---------------------------------------------------


def test_zero_amount_is_rejected_with_zero_amount_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="0.00"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.ZERO_AMOUNT in outcome.reason_codes


def test_negative_amount_is_rejected_with_negative_amount_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="-50.00"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.NEGATIVE_AMOUNT in outcome.reason_codes


def test_amount_over_overdue_balance_is_rejected_with_over_balance_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_amount="950.00", overdue_amount=Money("900.00")), provider, clock
    )

    assert outcome.valid is False
    assert ReasonCode.OVER_BALANCE in outcome.reason_codes


def test_amount_with_more_than_two_decimals_is_rejected_with_over_precision_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="250.125"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.OVER_PRECISION in outcome.reason_codes


def test_amount_below_policy_minimum_is_rejected_with_below_min_amount_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="5.00"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.BELOW_MIN_AMOUNT in outcome.reason_codes


def test_amount_at_the_overdue_balance_ceiling_is_accepted(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_amount="900.00", overdue_amount=Money("900.00")), provider, clock
    )

    assert ReasonCode.OVER_BALANCE not in outcome.reason_codes


def test_amount_at_the_policy_minimum_is_accepted(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="10.00"), provider, clock)

    assert ReasonCode.BELOW_MIN_AMOUNT not in outcome.reason_codes


# --- AC2: date checks ------------------------------------------------------


def test_past_date_is_rejected_with_past_date_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_date=_TODAY - timedelta(days=1)), provider, clock
    )

    assert outcome.valid is False
    assert ReasonCode.PAST_DATE in outcome.reason_codes


def test_date_beyond_policy_window_is_rejected_with_outside_window_reason_code(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_date=_TODAY + timedelta(days=31)), provider, clock
    )

    assert outcome.valid is False
    assert ReasonCode.OUTSIDE_WINDOW in outcome.reason_codes


def test_date_exactly_on_the_last_permitted_day_is_accepted(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_date=_TODAY + timedelta(days=30)), provider, clock
    )

    assert ReasonCode.OUTSIDE_WINDOW not in outcome.reason_codes
    assert ReasonCode.PAST_DATE not in outcome.reason_codes


def test_date_exactly_today_is_accepted(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_date=_TODAY), provider, clock)

    assert ReasonCode.PAST_DATE not in outcome.reason_codes


def test_fully_valid_input_returns_valid_true_with_no_reason_codes(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(), provider, clock)

    assert outcome.valid is True
    assert outcome.reason_codes == []
    assert outcome.alternatives is None


def test_amount_and_date_violations_are_both_reported_simultaneously(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_amount="0.00", promised_date=_TODAY - timedelta(days=1)),
        provider,
        clock,
    )

    assert outcome.valid is False
    assert ReasonCode.ZERO_AMOUNT in outcome.reason_codes
    assert ReasonCode.PAST_DATE in outcome.reason_codes
    assert len(outcome.reason_codes) == 2


# --- AC3: alternatives ------------------------------------------------------


def test_amount_rejection_includes_a_valid_amount_range_alternative(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="0.00"), provider, clock)

    assert outcome.alternatives is not None
    assert outcome.alternatives.valid_amount_range is not None
    assert outcome.alternatives.valid_amount_range.min == Money("10.00")
    assert outcome.alternatives.valid_amount_range.max == _OVERDUE_AMOUNT


def test_date_rejection_includes_a_valid_date_range_alternative(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(
        _input(promised_date=_TODAY - timedelta(days=1)), provider, clock
    )

    assert outcome.alternatives is not None
    assert outcome.alternatives.valid_date_range is not None
    assert outcome.alternatives.valid_date_range.earliest == _TODAY
    assert outcome.alternatives.valid_date_range.latest == _TODAY + timedelta(days=30)


def test_amount_rejection_does_not_include_a_date_range_alternative(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="0.00"), provider, clock)

    assert outcome.alternatives is not None
    assert outcome.alternatives.valid_date_range is None


# --- Fail-closed on unavailable policy --------------------------------------


def test_returns_policy_unavailable_reason_code_when_no_active_policy(
    clock: SimulatedClock,
) -> None:
    empty_provider = PolicyProvider()

    outcome = validate_ptp(_input(), empty_provider, clock)

    assert outcome.valid is False
    assert outcome.reason_codes == [ReasonCode.POLICY_UNAVAILABLE]


# --- MoneyValidationError translation at the function boundary -------------


def test_raw_negative_amount_string_is_translated_not_raised(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="-1.00"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.NEGATIVE_AMOUNT in outcome.reason_codes


def test_non_numeric_amount_string_is_translated_to_field_invalid(
    provider: PolicyProvider, clock: SimulatedClock
) -> None:
    outcome = validate_ptp(_input(promised_amount="not-a-number"), provider, clock)

    assert outcome.valid is False
    assert ReasonCode.FIELD_INVALID in outcome.reason_codes
