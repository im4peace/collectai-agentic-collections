"""Tests for the PaymentEvent domain model (data-models.md PaymentEvent)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from collectai.types.enums import PaymentOutcome, PaymentSource, Persona
from collectai.types.models import PaymentEvent


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
        "proposal_id": "prp_01J8ZK5D2E",
        "created_by_persona": Persona.CUSTOMER,
    }
    fields.update(overrides)
    return PaymentEvent.model_validate(fields)


def test_payment_event_holds_typed_money_and_enum_fields() -> None:
    event = _payment_event()
    assert event.amount.amount == Decimal("150.00")
    assert event.outcome is PaymentOutcome.SUCCEEDED
    assert event.source is PaymentSource.CUSTOMER_CHAT


def test_payment_event_simulated_must_be_true() -> None:
    with pytest.raises(ValidationError):
        _payment_event(simulated=False)


def test_payment_event_amount_must_be_strictly_positive() -> None:
    with pytest.raises(ValidationError):
        _payment_event(amount=Decimal("0.00"))


def test_payment_event_balance_after_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        _payment_event(balance_after=Decimal("-1.00"))


def test_payment_event_optional_links_may_be_none() -> None:
    event = _payment_event(applied_to_ptp_id=None, proposal_id=None)
    assert event.applied_to_ptp_id is None
    assert event.proposal_id is None


def test_payment_event_outcome_rejects_value_outside_succeeded_or_failed() -> None:
    with pytest.raises(ValidationError):
        _payment_event(outcome="PENDING")
