"""Deterministic payment arrangement eligibility service (E2-S3).

Given an account's overdue amount, days-past-due and conflicting-item state,
decides whether a standard installment arrangement can be offered, builds
the exact-sum installment schedule for each policy-permitted installment
count (AC1, math in `_schedule.py`), and classifies customer-requested terms
as `ELIGIBLE` or `EXCEPTIONAL` against the active `PolicyRuleSet` (AC3,
logic in `_classification.py`). CLAUDE.md: exact-sum schedule math is
deterministic calculation, never delegated to an LLM.

Every public function is fail-closed (AC5): if `PolicyProvider.get_active()`
raises `PolicyUnavailable`, this module returns a `RuleResult.fail(...)`
carrying no options and no guess.

Public surface (re-exported so callers need not know about the split):
`get_eligible_options`, `classify_requested_terms`, `ScheduleEntry`,
`ArrangementOption`, `RequestedTerms`, `EligibilityResult`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from collectai.config.policy.models import ArrangementParameters, PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.arrangement._classification import classify_requested
from collectai.rules_engine.arrangement._schedule import build_eligible_options
from collectai.rules_engine.arrangement._types import (
    ArrangementOption,
    EligibilityResult,
    RequestedTerms,
    ScheduleEntry,
)
from collectai.types.clock import Clock
from collectai.types.enums import EligibilityClass
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable, RuleFailure, RuleResult

__all__ = [
    "ArrangementOption",
    "EligibilityResult",
    "RequestedTerms",
    "ScheduleEntry",
    "classify_requested_terms",
    "get_eligible_options",
]


def get_eligible_options(
    provider: PolicyProvider,
    clock: Clock,
    overdue_amount: Money,
    dpd: int,
    has_active_ptp: bool,
    has_active_arrangement: bool,
) -> RuleResult[EligibilityResult]:
    """Return the stable list of standard installment options for an account.

    Deterministic (AC1): the same inputs, `PolicyRuleSet` version and `Clock`
    always produce the identical option list, in the same order. Returns
    `NOT_ELIGIBLE` with an empty option list and a reason code (AC2, AC4)
    when the account fails eligibility. Fails closed (AC5) when no policy is
    active.
    """
    try:
        policy = provider.get_active()
    except PolicyUnavailable as exc:
        return RuleResult.fail(_policy_unavailable_failure(exc))

    today = clock.now().date()
    result = _evaluate_eligibility(
        policy, today, overdue_amount, dpd, has_active_ptp, has_active_arrangement
    )
    return RuleResult.success(result)


def classify_requested_terms(
    provider: PolicyProvider,
    clock: Clock,
    overdue_amount: Money,
    dpd: int,
    has_active_ptp: bool,
    has_active_arrangement: bool,
    requested_terms: RequestedTerms,
) -> RuleResult[EligibilityResult]:
    """Classify customer-requested terms as `ELIGIBLE` or `EXCEPTIONAL` (AC3).

    An account that fails base eligibility (AC2, AC4) stays `NOT_ELIGIBLE`
    regardless of the request. Fails closed (AC5) when no policy is active.
    """
    try:
        policy = provider.get_active()
    except PolicyUnavailable as exc:
        return RuleResult.fail(_policy_unavailable_failure(exc))

    today = clock.now().date()
    base = _evaluate_eligibility(
        policy, today, overdue_amount, dpd, has_active_ptp, has_active_arrangement
    )
    if base.classification == EligibilityClass.NOT_ELIGIBLE:
        return RuleResult.success(_with_requested_terms(base, requested_terms))

    classified = classify_requested(policy, today, overdue_amount, base, requested_terms)
    return RuleResult.success(classified)


def _with_requested_terms(
    base: EligibilityResult, requested_terms: RequestedTerms
) -> EligibilityResult:
    return replace(base, requested_terms=requested_terms)


def _policy_unavailable_failure(exc: PolicyUnavailable) -> RuleFailure:
    return RuleFailure(
        reason_code=exc.reason_code,
        message=str(exc),
        details={"policy_version": None},
    )


def _evaluate_eligibility(
    policy: PolicyRuleSet,
    today: date,
    overdue_amount: Money,
    dpd: int,
    has_active_ptp: bool,
    has_active_arrangement: bool,
) -> EligibilityResult:
    arrangement = policy.parameters.arrangement
    reason = _blocking_reason(
        arrangement, overdue_amount, dpd, has_active_ptp, has_active_arrangement
    )
    if reason is not None:
        return _not_eligible_result(reason)

    first_date = today + timedelta(days=1)
    options = build_eligible_options(arrangement, overdue_amount, first_date)
    if not options:
        return _not_eligible_result(ReasonCode.BELOW_MIN_AMOUNT)

    return EligibilityResult(
        classification=EligibilityClass.ELIGIBLE,
        reason_code=None,
        options=options,
        requested_terms=None,
        exception_types=[],
        within_reviewer_thresholds=None,
        permitted_paths=[],
    )


def _not_eligible_result(reason: ReasonCode) -> EligibilityResult:
    return EligibilityResult(
        classification=EligibilityClass.NOT_ELIGIBLE,
        reason_code=reason,
        options=[],
        requested_terms=None,
        exception_types=[],
        within_reviewer_thresholds=None,
        permitted_paths=_permitted_paths_for(reason),
    )


def _blocking_reason(
    arrangement: ArrangementParameters,
    overdue_amount: Money,
    dpd: int,
    has_active_ptp: bool,
    has_active_arrangement: bool,
) -> ReasonCode | None:
    if dpd > arrangement.eligible_max_dpd:
        return ReasonCode.EXCEEDS_THRESHOLD
    if overdue_amount < arrangement.min_overdue_amount:
        return ReasonCode.BELOW_MIN_AMOUNT
    has_conflict = has_active_ptp or has_active_arrangement
    if has_conflict and not arrangement.allow_with_active_ptp:
        return ReasonCode.CONFLICTING_ACTIVE_ITEM
    return None


def _permitted_paths_for(reason: ReasonCode) -> list[str]:
    if reason == ReasonCode.CONFLICTING_ACTIVE_ITEM:
        return ["AMEND", "CANCEL"]
    return []
