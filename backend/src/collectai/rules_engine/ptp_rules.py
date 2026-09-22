"""Deterministic PTP amount/date validation and the PTP satisfaction rule.

Both services are pure functions over typed inputs plus the active
`PolicyRuleSet` (specs/design/component-map.md E2-S2). No financial decision
here is ever delegated to an LLM (CLAUDE.md "Core Engineering Principle").

`evaluate_satisfaction` is deliberately given the *full* list of a payment
event's candidate `PaymentEvent`s (not pre-filtered by the caller) and
filters by `applied_to_ptp_id` itself, so a caller can pass "every event for
this account" without needing to know the association rule.

NOTE: this file is nearing the 300-line block threshold (code-gen skill,
principle #1). If it grows further, split `validate_ptp` and its amount/date
check helpers into `ptp_rules/validation.py` and `evaluate_satisfaction` and
its helpers into `ptp_rules/satisfaction.py`, re-exporting both from this
module (or a `ptp_rules/__init__.py`) so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.types.clock import Clock
from collectai.types.enums import PaymentOutcome, PtpStatus
from collectai.types.models import PaymentEvent, PromiseToPay
from collectai.types.money import Money, MoneyValidationError
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

RawAmount = Money | Decimal | int | str

_ZERO: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class PtpValidationInput:
    """Inputs for `validate_ptp`.

    `promised_amount` accepts a raw `Decimal`/`str`/`int` as well as an
    already-constructed `Money`, so a caller's unvalidated request payload
    can be passed straight through without pre-parsing it into `Money`.
    """

    promised_amount: RawAmount
    promised_date: date
    overdue_amount: Money


@dataclass(frozen=True, slots=True)
class AmountRange:
    min: Money
    max: Money


@dataclass(frozen=True, slots=True)
class DateRange:
    earliest: date
    latest: date


@dataclass(frozen=True, slots=True)
class Alternatives:
    valid_amount_range: AmountRange | None = None
    valid_date_range: DateRange | None = None


@dataclass(frozen=True, slots=True)
class PtpValidationOutcome:
    """Rules-engine-level PTP validation result (mirrors the field naming of
    the future API-layer `PtpValidationResult` in api-contracts.md, without
    being that schema)."""

    valid: bool
    reason_codes: list[ReasonCode]
    alternatives: Alternatives | None


@dataclass(frozen=True, slots=True)
class SatisfactionOutcome:
    status: PtpStatus
    cumulative_paid: Money
    remaining_amount: Money


def validate_ptp(
    validation_input: PtpValidationInput,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> PtpValidationOutcome:
    """Validate a proposed PTP amount and date against the active policy.

    Fail-closed: if no `PolicyRuleSet` is active, returns
    `valid=False, reason_codes=[POLICY_UNAVAILABLE]` rather than raising.
    """
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable:
        return PtpValidationOutcome(
            valid=False, reason_codes=[ReasonCode.POLICY_UNAVAILABLE], alternatives=None
        )

    amount_reason = _check_amount(
        validation_input.promised_amount,
        validation_input.overdue_amount,
        policy.parameters.ptp.min_amount,
    )
    date_reason = _check_date(
        validation_input.promised_date, clock, policy.parameters.ptp.window_days
    )

    reason_codes = [code for code in (amount_reason, date_reason) if code is not None]
    if not reason_codes:
        return PtpValidationOutcome(valid=True, reason_codes=[], alternatives=None)

    alternatives = _build_alternatives(
        amount_reason=amount_reason,
        date_reason=date_reason,
        overdue_amount=validation_input.overdue_amount,
        min_amount=policy.parameters.ptp.min_amount,
        clock=clock,
        window_days=policy.parameters.ptp.window_days,
    )
    return PtpValidationOutcome(valid=False, reason_codes=reason_codes, alternatives=alternatives)


def _parse_promised_amount(raw_amount: RawAmount) -> tuple[Money | None, ReasonCode | None]:
    """Construct `Money`, translating a `MoneyValidationError` into a reason
    code instead of letting it propagate past `validate_ptp`."""
    if isinstance(raw_amount, Money):
        return raw_amount, None
    try:
        return Money(raw_amount), None
    except MoneyValidationError as exc:
        return None, exc.reason_code


def _check_amount_not_zero(amount: Money) -> ReasonCode | None:
    return ReasonCode.ZERO_AMOUNT if amount.amount == _ZERO else None


def _check_amount_within_balance(amount: Money, overdue_amount: Money) -> ReasonCode | None:
    return ReasonCode.OVER_BALANCE if amount > overdue_amount else None


def _check_amount_meets_minimum(amount: Money, min_amount: Money) -> ReasonCode | None:
    return ReasonCode.BELOW_MIN_AMOUNT if amount < min_amount else None


def _check_amount(
    raw_amount: RawAmount, overdue_amount: Money, min_amount: Money
) -> ReasonCode | None:
    amount, parse_reason = _parse_promised_amount(raw_amount)
    if amount is None:
        return parse_reason
    return (
        _check_amount_not_zero(amount)
        or _check_amount_within_balance(amount, overdue_amount)
        or _check_amount_meets_minimum(amount, min_amount)
    )


def _check_date_not_past(promised_date: date, today: date) -> ReasonCode | None:
    return ReasonCode.PAST_DATE if promised_date < today else None


def _check_date_within_window(
    promised_date: date, today: date, window_days: int
) -> ReasonCode | None:
    latest = today + timedelta(days=window_days)
    return ReasonCode.OUTSIDE_WINDOW if promised_date > latest else None


def _check_date(promised_date: date, clock: Clock, window_days: int) -> ReasonCode | None:
    today = clock.now().date()
    return _check_date_not_past(promised_date, today) or _check_date_within_window(
        promised_date, today, window_days
    )


def _build_alternatives(
    *,
    amount_reason: ReasonCode | None,
    date_reason: ReasonCode | None,
    overdue_amount: Money,
    min_amount: Money,
    clock: Clock,
    window_days: int,
) -> Alternatives:
    valid_amount_range = (
        AmountRange(min=min_amount, max=overdue_amount) if amount_reason is not None else None
    )
    valid_date_range: DateRange | None = None
    if date_reason is not None:
        today = clock.now().date()
        valid_date_range = DateRange(earliest=today, latest=today + timedelta(days=window_days))
    return Alternatives(valid_amount_range=valid_amount_range, valid_date_range=valid_date_range)


def evaluate_satisfaction(
    ptp: PromiseToPay,
    payment_events: list[PaymentEvent],
    policy: PolicyRuleSet,
    clock: Clock,
) -> SatisfactionOutcome:
    """Sum qualifying payments for `ptp` and derive its KEPT/PENDING/BROKEN
    status.

    A `PaymentEvent` qualifies when it is `SUCCEEDED`, `applied_to_ptp_id`
    matches `ptp.ptp_id`, its amount is at or above
    `policy.parameters.ptp.qualifying_payment_min_amount`, and it occurred on
    or before `ptp.promised_date` (AC5, AC7).
    """
    qualifying_events = [
        event
        for event in payment_events
        if _is_qualifying_event(event, ptp, policy.parameters.ptp.qualifying_payment_min_amount)
    ]
    cumulative_paid = _sum_amounts(qualifying_events)
    remaining_amount = _remaining_amount(ptp.promised_amount, cumulative_paid)
    status = _determine_status(ptp.promised_amount, cumulative_paid, ptp.promised_date, clock)
    return SatisfactionOutcome(
        status=status, cumulative_paid=cumulative_paid, remaining_amount=remaining_amount
    )


def _is_qualifying_event(
    event: PaymentEvent, ptp: PromiseToPay, qualifying_min_amount: Money
) -> bool:
    return (
        event.applied_to_ptp_id == ptp.ptp_id
        and event.outcome is PaymentOutcome.SUCCEEDED
        and event.amount >= qualifying_min_amount
        and event.occurred_at.date() <= ptp.promised_date
    )


def _sum_amounts(events: list[PaymentEvent]) -> Money:
    total = Money("0")
    for event in events:
        total = total + event.amount
    return total


def _remaining_amount(promised_amount: Money, cumulative_paid: Money) -> Money:
    difference = promised_amount.amount - cumulative_paid.amount
    return Money(max(difference, _ZERO))


def _determine_status(
    promised_amount: Money, cumulative_paid: Money, promised_date: date, clock: Clock
) -> PtpStatus:
    if cumulative_paid >= promised_amount:
        return PtpStatus.KEPT
    if clock.now().date() > promised_date:
        return PtpStatus.BROKEN
    return PtpStatus.PENDING
