"""Tests for the generic rule-result vocabulary (results.py)."""

from __future__ import annotations

import pytest

from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable, RuleFailure, RuleResult


def test_rule_result_success_is_ok_and_carries_the_value() -> None:
    result: RuleResult[int] = RuleResult.success(42)
    assert result.ok is True
    assert result.value == 42
    assert result.failure is None


def test_rule_result_fail_is_not_ok_and_carries_the_failure() -> None:
    failure = RuleFailure(reason_code=ReasonCode.OVER_BALANCE, message="Amount exceeds balance.")
    result: RuleResult[int] = RuleResult.fail(failure)
    assert result.ok is False
    assert result.value is None
    assert result.failure is failure


def test_rule_failure_carries_reason_code_message_and_optional_details() -> None:
    failure = RuleFailure(
        reason_code=ReasonCode.BELOW_MIN_AMOUNT,
        message="Amount is below the policy minimum.",
        details={"minimum": "25.00"},
    )
    assert failure.reason_code is ReasonCode.BELOW_MIN_AMOUNT
    assert failure.message == "Amount is below the policy minimum."
    assert failure.details == {"minimum": "25.00"}


def test_rule_failure_details_defaults_to_none() -> None:
    failure = RuleFailure(reason_code=ReasonCode.PAST_DATE, message="Date is in the past.")
    assert failure.details is None


def test_policy_unavailable_carries_the_fixed_policy_unavailable_reason_code() -> None:
    error = PolicyUnavailable()
    assert error.reason_code is ReasonCode.POLICY_UNAVAILABLE


def test_policy_unavailable_is_raisable_as_an_exception() -> None:
    with pytest.raises(PolicyUnavailable) as excinfo:
        raise PolicyUnavailable("No active PolicyRuleSet.")
    assert excinfo.value.reason_code is ReasonCode.POLICY_UNAVAILABLE
    assert "No active PolicyRuleSet." in str(excinfo.value)
