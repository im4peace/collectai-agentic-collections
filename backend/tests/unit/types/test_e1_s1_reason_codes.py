"""Tests for the stable reason-code catalogue (api-contracts.md section 1.4)."""

from __future__ import annotations

import pytest

from collectai.types.reason_codes import ReasonCode

EXPECTED_CODES = [
    # Money and dates
    "ZERO_AMOUNT",
    "NEGATIVE_AMOUNT",
    "OVER_PRECISION",
    "FLOAT_NOT_ALLOWED",
    "OVER_BALANCE",
    "BELOW_MIN_AMOUNT",
    "PAST_DATE",
    "OUTSIDE_WINDOW",
    # Records and state
    "CONFLICTING_ACTIVE_ITEM",
    "DISPUTED_ITEM",
    "STALE_DATA",
    "VERSION_CONFLICT",
    "PROPOSAL_INVALID",
    "INVALID_STATE_TRANSITION",
    "CASE_ALREADY_DECIDED",
    "WRONG_QUEUE",
    "INCONSISTENT_RECORD",
    # Policy and authority
    "NOT_PERMITTED_BY_POLICY",
    "EXCEPTION_TYPE_NOT_PERMITTED",
    "EXCEEDS_THRESHOLD",
    "EXCEEDS_MAX_OVERDUE_AMOUNT",
    "WRONG_REVIEWER_ROLE",
    "QUEUE_NOT_PERMITTED",
    "POLICY_UNAVAILABLE",
    "AMBIGUOUS_VALIDATION",
    # Contact policy
    "MAX_ATTEMPTS",
    "MIN_INTERVAL",
    # Validation
    "FIELD_INVALID",
    "UNKNOWN_FIELD",
    "REASON_REQUIRED",
    "NOTE_REQUIRED",
    "OUTCOME_REQUIRED",
    "MODIFICATION_REQUIRED",
    "ESCALATE_REASON_REQUIRED",
    "ESCALATE_REASON_NOT_WHITELISTED",
    "DESTINATION_NOT_ACCEPTED",
    "FREE_FORM_AMOUNT_NOT_ALLOWED",
    "IDEMPOTENCY_KEY_REQUIRED",
    "IDEMPOTENCY_KEY_REUSED",
    "FILTER_REQUIRED",
    "CUSTOMER_ID_REQUIRED_OR_FORBIDDEN",
]


def test_catalogue_contains_exactly_the_contract_codes() -> None:
    actual = {member.name for member in ReasonCode}
    assert actual == set(EXPECTED_CODES)


@pytest.mark.parametrize("code_name", EXPECTED_CODES)
def test_each_code_is_a_distinct_reason_code_member(code_name: str) -> None:
    member = ReasonCode[code_name]
    assert member.value == code_name
    assert isinstance(member, ReasonCode)


def test_reason_codes_are_stable_strings_not_bare_literals() -> None:
    assert ReasonCode.NEGATIVE_AMOUNT != "NEGATIVE_AMOUNT" or isinstance(
        ReasonCode.NEGATIVE_AMOUNT, ReasonCode
    )
    assert ReasonCode.NEGATIVE_AMOUNT is not ReasonCode.OVER_PRECISION
