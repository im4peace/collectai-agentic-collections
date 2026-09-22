"""Tests for the payable-amounts function (E2-S2 AC4)."""

from __future__ import annotations

from datetime import UTC, datetime

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.models import PolicyRuleSet
from collectai.rules_engine.payable import get_payable_options
from collectai.types.clock import SimulatedClock
from collectai.types.enums import PayableOptionType
from collectai.types.money import Money

_OVERDUE_AMOUNT = Money("900.00")
_OUTSTANDING_BALANCE = Money("8200.00")


def _seed_policy() -> PolicyRuleSet:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    return load_seed_policy_v1(clock)


def test_returns_overdue_amount_and_full_balance_as_decimal_strings() -> None:
    options = get_payable_options(
        overdue_amount=_OVERDUE_AMOUNT,
        outstanding_balance=_OUTSTANDING_BALANCE,
        is_suppressed=False,
        policy=_seed_policy(),
    )

    by_type = {option.option_type: option.amount for option in options}
    assert by_type[PayableOptionType.OVERDUE_AMOUNT].to_api_string() == "900.00"
    assert by_type[PayableOptionType.FULL_BALANCE].to_api_string() == "8200.00"


def test_returns_one_option_per_enabled_payable_option_type() -> None:
    policy = _seed_policy()
    options = get_payable_options(
        overdue_amount=_OVERDUE_AMOUNT,
        outstanding_balance=_OUTSTANDING_BALANCE,
        is_suppressed=False,
        policy=policy,
    )

    assert len(options) == len(policy.parameters.payment.payable_options)


def test_returns_no_options_for_an_account_under_suppression() -> None:
    options = get_payable_options(
        overdue_amount=_OVERDUE_AMOUNT,
        outstanding_balance=_OUTSTANDING_BALANCE,
        is_suppressed=True,
        policy=_seed_policy(),
    )

    assert options == []
