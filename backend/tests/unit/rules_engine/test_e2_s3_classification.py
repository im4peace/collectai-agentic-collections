"""Tests for `classify_requested_terms` (E2-S3 AC3, plus AC5 on this entry point)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.arrangement import RequestedTerms, classify_requested_terms
from collectai.types.clock import SimulatedClock
from collectai.types.enums import EligibilityClass, ExceptionType
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_TODAY_INSTANT = datetime(2026, 10, 19, tzinfo=UTC)
_TODAY = date(2026, 10, 19)


def _active_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


def test_requested_terms_matching_a_standard_option_are_classified_eligible() -> None:
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=3,
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.ELIGIBLE
    assert result.value.exception_types == []
    assert result.value.within_reviewer_thresholds is None
    assert result.value.requested_terms == requested
    assert [opt.installment_count for opt in result.value.options] == [3, 6, 12]


def test_requested_installment_count_outside_standard_options_is_exceptional_term() -> None:
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=4,
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.EXCEPTIONAL
    assert result.value.exception_types == [ExceptionType.TERM]
    assert result.value.within_reviewer_thresholds is True


def test_requested_date_beyond_standard_delay_is_exceptional_start_date() -> None:
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=3,
        first_installment_date=_TODAY + timedelta(days=35),  # standard max is 30 days
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.EXCEPTIONAL
    assert result.value.exception_types == [ExceptionType.START_DATE]
    assert result.value.within_reviewer_thresholds is True  # exception ceiling is 60 days


def test_requested_amount_not_matching_exact_sum_schedule_is_exceptional_amount_structure() -> None:
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=3,
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=Money("300.00"),  # exact-sum math gives 256.80
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.EXCEPTIONAL
    assert result.value.exception_types == [ExceptionType.AMOUNT_STRUCTURE]
    assert result.value.within_reviewer_thresholds is True


def test_request_beyond_exception_thresholds_is_exceptional_but_not_within_thresholds() -> None:
    """A request beyond even exception.thresholds.* is EXCEPTIONAL, not NOT_ELIGIBLE;
    approval authority is a separate, later concern (E7-S2/E7-S4)."""
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=30,  # exception ceiling is max_installment_count=24
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.EXCEPTIONAL
    assert ExceptionType.TERM in result.value.exception_types
    assert result.value.within_reviewer_thresholds is False


def test_multiple_simultaneous_exception_types_are_reported_without_duplicates() -> None:
    """AC3: a request can have multiple exception types simultaneously."""
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=4,  # TERM
        first_installment_date=_TODAY + timedelta(days=70),  # START_DATE, beyond 60-day ceiling
        installment_amount=Money("999.99"),  # AMOUNT_STRUCTURE
    )

    result = classify_requested_terms(
        provider, clock, Money("770.40"), 34, False, False, requested
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.EXCEPTIONAL
    assert set(result.value.exception_types) == {
        ExceptionType.TERM,
        ExceptionType.START_DATE,
        ExceptionType.AMOUNT_STRUCTURE,
    }
    assert len(result.value.exception_types) == 3  # each type reported at most once
    assert result.value.within_reviewer_thresholds is False  # date exceeds the 60-day ceiling


def test_not_eligible_account_stays_not_eligible_regardless_of_requested_terms() -> None:
    """A request cannot rescue an account that fails base eligibility (AC2, AC4)."""
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = _active_provider(clock)
    requested = RequestedTerms(
        installment_count=3,
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider,
        clock,
        Money("500.00"),
        dpd=95,  # beyond eligible_max_dpd=89
        has_active_ptp=False,
        has_active_arrangement=False,
        requested_terms=requested,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.classification == EligibilityClass.NOT_ELIGIBLE
    assert result.value.reason_code == ReasonCode.EXCEEDS_THRESHOLD
    assert result.value.options == []
    assert result.value.exception_types == []
    assert result.value.requested_terms == requested


def test_classify_requested_terms_fails_closed_when_policy_unavailable() -> None:
    """AC5 on the classification entry point too: no guessing without a policy."""
    clock = SimulatedClock(_TODAY_INSTANT)
    provider = PolicyProvider()  # never activated
    requested = RequestedTerms(
        installment_count=3,
        first_installment_date=_TODAY + timedelta(days=6),
        installment_amount=None,
    )

    result = classify_requested_terms(
        provider, clock, Money("500.00"), 10, False, False, requested
    )

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE
