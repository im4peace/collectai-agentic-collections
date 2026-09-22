"""Tests for the PTP satisfaction rule (E2-S2 AC5, AC6, AC7)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.models import PolicyRuleSet
from collectai.rules_engine.ptp_rules import evaluate_satisfaction
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.enums.ptp_payment import PaymentOutcome, PaymentSource
from collectai.types.models import PaymentEvent, PromiseToPay

_PROMISED_DATE = date(2026, 10, 15)


def _ptp(**overrides: object) -> PromiseToPay:
    fields: dict[str, object] = {
        "ptp_id": "ptp_01J8ZK3M2Q",
        "account_id": "acc_000123",
        "customer_id": "cus_000101",
        "item_id": None,
        "promised_amount": Decimal("250.00"),
        "promised_date": _PROMISED_DATE,
        "status": PtpStatus.PENDING,
        "cumulative_paid": Decimal("0.00"),
        "interaction_reference": "conv_01J8ZK4A9B",
        "source": PtpSource.CUSTOMER_CHAT,
        "created_by_persona": Persona.CUSTOMER,
        "created_at": datetime(2026, 10, 1, 9, 5, tzinfo=UTC),
        "updated_at": datetime(2026, 10, 1, 9, 5, tzinfo=UTC),
        "kept_at": None,
        "broken_at": None,
        "cancelled_at": None,
        "cancel_reason": None,
        "policy_version": "policy-v1",
        "version": 1,
    }
    fields.update(overrides)
    return PromiseToPay.model_validate(fields)


def _payment_event(**overrides: object) -> PaymentEvent:
    fields: dict[str, object] = {
        "payment_event_id": "pay_01J8ZK6R1T",
        "account_id": "acc_000123",
        "customer_id": "cus_000101",
        "amount": Decimal("150.00"),
        "outcome": PaymentOutcome.SUCCEEDED,
        "source": PaymentSource.CUSTOMER_CHAT,
        "simulated": True,
        "occurred_at": datetime(2026, 10, 5, 10, 0, tzinfo=UTC),
        "balance_after": Decimal("8270.75"),
        "applied_to_ptp_id": "ptp_01J8ZK3M2Q",
        "proposal_id": None,
        "created_by_persona": Persona.CUSTOMER,
    }
    fields.update(overrides)
    return PaymentEvent.model_validate(fields)


def _seed_policy_and_clock(instant: datetime) -> tuple[PolicyRuleSet, SimulatedClock]:
    clock = SimulatedClock(instant)
    return load_seed_policy_v1(clock), clock


# --- AC5 / AC6: KEPT / PENDING / BROKEN -------------------------------------


def test_no_qualifying_payments_before_deadline_returns_pending() -> None:
    ptp = _ptp()
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 5, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, [], policy, clock)

    assert outcome.status is PtpStatus.PENDING


def test_single_qualifying_payment_below_promised_amount_returns_pending(
) -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("100.00"))]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 5, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.PENDING
    assert outcome.cumulative_paid.to_api_string() == "100.00"
    assert outcome.remaining_amount.to_api_string() == "150.00"


def test_second_payment_bringing_total_to_promised_amount_returns_kept() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [
        _payment_event(payment_event_id="pay_01J8ZK6R1T", amount=Decimal("100.00")),
        _payment_event(payment_event_id="pay_01J8ZK6R2U", amount=Decimal("150.00")),
    ]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 10, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.KEPT
    assert outcome.cumulative_paid.to_api_string() == "250.00"
    assert outcome.remaining_amount.to_api_string() == "0.00"


def test_cumulative_total_exceeding_promised_amount_returns_kept() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("300.00"))]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 10, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.KEPT


def test_short_total_after_the_deadline_returns_broken() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("100.00"))]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 16, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.BROKEN
    assert outcome.cumulative_paid.to_api_string() == "100.00"
    assert outcome.remaining_amount.to_api_string() == "150.00"


def test_full_total_reached_exactly_on_the_deadline_still_returns_kept() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [
        _payment_event(
            amount=Decimal("250.00"), occurred_at=datetime(2026, 10, 15, 23, 0, tzinfo=UTC)
        )
    ]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 16, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.KEPT


# --- AC7: exclusions ---------------------------------------------------------


def test_failed_payment_events_are_excluded_from_the_cumulative_total() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("250.00"), outcome=PaymentOutcome.FAILED)]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 5, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.PENDING
    assert outcome.cumulative_paid.to_api_string() == "0.00"


def test_payment_below_the_qualifying_minimum_is_excluded_from_the_cumulative_total(
) -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("2.00"))]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 5, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.cumulative_paid.to_api_string() == "0.00"


def test_payment_dated_after_the_due_date_is_excluded_from_the_cumulative_total(
) -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [
        _payment_event(
            amount=Decimal("250.00"), occurred_at=datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
        )
    ]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 20, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.status is PtpStatus.BROKEN
    assert outcome.cumulative_paid.to_api_string() == "0.00"


def test_payment_events_applied_to_a_different_ptp_are_excluded() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"))
    events = [_payment_event(amount=Decimal("250.00"), applied_to_ptp_id="ptp_01J8ZK9X7L")]
    policy, clock = _seed_policy_and_clock(datetime(2026, 10, 5, tzinfo=UTC))

    outcome = evaluate_satisfaction(ptp, events, policy, clock)

    assert outcome.cumulative_paid.to_api_string() == "0.00"
