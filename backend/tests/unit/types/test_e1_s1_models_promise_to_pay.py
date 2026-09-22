"""Tests for the PromiseToPay domain model (data-models.md PromiseToPay, AC4)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from collectai.types.enums import Persona, PtpSource, PtpStatus
from collectai.types.models import PromiseToPay


def _ptp(**overrides: object) -> PromiseToPay:
    fields: dict[str, object] = {
        "ptp_id": "ptp_01J8ZK3M2Q",
        "account_id": "acc_000123",
        "customer_id": "cus_000101",
        "item_id": None,
        "promised_amount": Decimal("250.00"),
        "promised_date": date(2026, 10, 15),
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


def test_ptp_status_accepts_only_the_four_lifecycle_values() -> None:
    for status in (PtpStatus.PENDING, PtpStatus.KEPT, PtpStatus.BROKEN, PtpStatus.CANCELLED):
        kwargs: dict[str, object] = {"status": status}
        if status is PtpStatus.KEPT:
            kwargs["kept_at"] = datetime(2026, 10, 16, tzinfo=UTC)
        if status is PtpStatus.BROKEN:
            kwargs["broken_at"] = datetime(2026, 10, 16, tzinfo=UTC)
        if status is PtpStatus.CANCELLED:
            kwargs["cancelled_at"] = datetime(2026, 10, 16, tzinfo=UTC)
            kwargs["cancel_reason"] = "Customer requested cancellation."
        assert _ptp(**kwargs).status is status


def test_ptp_status_rejects_value_outside_the_catalogue() -> None:
    with pytest.raises(ValidationError):
        _ptp(status="EXPIRED")


def test_ptp_promised_amount_must_be_strictly_positive() -> None:
    with pytest.raises(ValidationError):
        _ptp(promised_amount=Decimal("0.00"))


def test_ptp_remaining_amount_is_derived_not_stored() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"), cumulative_paid=Decimal("100.00"))
    assert ptp.remaining_amount.amount == Decimal("150.00")


def test_ptp_remaining_amount_clamps_to_zero_when_overpaid() -> None:
    ptp = _ptp(promised_amount=Decimal("250.00"), cumulative_paid=Decimal("250.00"))
    assert ptp.remaining_amount.amount == Decimal("0.00")


def test_ptp_cancelled_requires_a_cancel_reason() -> None:
    with pytest.raises(ValidationError):
        _ptp(
            status=PtpStatus.CANCELLED,
            cancelled_at=datetime(2026, 10, 16, tzinfo=UTC),
            cancel_reason=None,
        )


def test_ptp_kept_requires_kept_at_to_be_set() -> None:
    with pytest.raises(ValidationError):
        _ptp(status=PtpStatus.KEPT, kept_at=None)
