"""Classify customer-requested arrangement terms against the active policy (AC3).

A request is `ELIGIBLE` when its installment count matches one of the
account's standard options and its first installment date falls within
`arrangement.max_start_delay_days`. Any deviation makes it `EXCEPTIONAL`,
with `exception_types` naming every dimension that deviated and
`within_reviewer_thresholds` reporting whether the request still sits inside
the broader `exception.thresholds.*` ceiling — a request beyond even that
ceiling is still classified `EXCEPTIONAL` (the *authority* to approve it is a
separate, later concern: E7-S2/E7-S4).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from collectai.config.policy.models import PolicyRuleSet
from collectai.rules_engine.arrangement._schedule import expected_regular_installment
from collectai.rules_engine.arrangement._types import (
    ArrangementOption,
    EligibilityResult,
    RequestedTerms,
)
from collectai.types.enums import EligibilityClass, ExceptionType
from collectai.types.money import Money


def _requested_count_is_standard(
    base_options: list[ArrangementOption], requested_count: int
) -> bool:
    return requested_count in {option.installment_count for option in base_options}


def _requested_date_within_window(today: date, requested_date: date, max_delay_days: int) -> bool:
    return today <= requested_date <= today + timedelta(days=max_delay_days)


def _requested_amount_matches_schedule(overdue_amount: Money, requested: RequestedTerms) -> bool:
    if requested.installment_amount is None:
        return True
    expected = expected_regular_installment(overdue_amount.amount, requested.installment_count)
    return expected is not None and Money(expected) == requested.installment_amount


def _compute_exception_types(
    policy: PolicyRuleSet,
    today: date,
    overdue_amount: Money,
    base_options: list[ArrangementOption],
    requested: RequestedTerms,
) -> list[ExceptionType]:
    exception_types: list[ExceptionType] = []
    if not _requested_count_is_standard(base_options, requested.installment_count):
        exception_types.append(ExceptionType.TERM)
    max_start_delay = policy.parameters.arrangement.max_start_delay_days
    if not _requested_date_within_window(today, requested.first_installment_date, max_start_delay):
        exception_types.append(ExceptionType.START_DATE)
    if not _requested_amount_matches_schedule(overdue_amount, requested):
        exception_types.append(ExceptionType.AMOUNT_STRUCTURE)
    return exception_types


def _reference_installment_amount(overdue_amount: Money, requested: RequestedTerms) -> Money | None:
    if requested.installment_amount is not None:
        return requested.installment_amount
    expected = expected_regular_installment(overdue_amount.amount, requested.installment_count)
    return Money(expected) if expected is not None else None


def _within_reviewer_thresholds(
    policy: PolicyRuleSet, today: date, overdue_amount: Money, requested: RequestedTerms
) -> bool:
    thresholds = policy.parameters.exception.thresholds
    count_ok = 2 <= requested.installment_count <= thresholds.max_installment_count
    date_ok = _requested_date_within_window(
        today, requested.first_installment_date, thresholds.max_start_delay_days
    )
    reference_amount = _reference_installment_amount(overdue_amount, requested)
    amount_ok = (
        reference_amount is not None and reference_amount >= thresholds.min_installment_amount
    )
    return count_ok and date_ok and amount_ok


def classify_requested(
    policy: PolicyRuleSet,
    today: date,
    overdue_amount: Money,
    base: EligibilityResult,
    requested: RequestedTerms,
) -> EligibilityResult:
    """Classify `requested` against `base` (an already-`ELIGIBLE` account)."""
    exception_types = _compute_exception_types(
        policy, today, overdue_amount, base.options, requested
    )
    if not exception_types:
        return replace(
            base,
            classification=EligibilityClass.ELIGIBLE,
            reason_code=None,
            requested_terms=requested,
            exception_types=[],
            within_reviewer_thresholds=None,
        )

    within = _within_reviewer_thresholds(policy, today, overdue_amount, requested)
    return replace(
        base,
        classification=EligibilityClass.EXCEPTIONAL,
        reason_code=None,
        requested_terms=requested,
        exception_types=exception_types,
        within_reviewer_thresholds=within,
    )
