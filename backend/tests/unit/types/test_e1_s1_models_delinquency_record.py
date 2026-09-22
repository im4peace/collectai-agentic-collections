"""Tests for the DelinquencyRecord domain model (data-models.md DelinquencyRecord)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from collectai.types.enums import Bucket, CollectionStatus
from collectai.types.models import DelinquencyRecord


def _record(**overrides: object) -> DelinquencyRecord:
    fields: dict[str, object] = {
        "account_id": "acc_000123",
        "customer_id": "cus_000101",
        "outstanding_balance": Decimal("8420.75"),
        "overdue_amount": Decimal("770.40"),
        "dpd": 34,
        "bucket": Bucket.DPD_30_59,
        "collection_status": CollectionStatus.IN_PROGRESS,
        "as_of": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        "record_version": 7,
        "updated_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return DelinquencyRecord.model_validate(fields)


def test_delinquency_record_holds_typed_money_and_enum_fields() -> None:
    record = _record()
    assert record.outstanding_balance.amount == Decimal("8420.75")
    assert record.overdue_amount.amount == Decimal("770.40")
    assert record.bucket is Bucket.DPD_30_59
    assert record.collection_status is CollectionStatus.IN_PROGRESS


def test_delinquency_record_rejects_negative_outstanding_balance() -> None:
    with pytest.raises(ValidationError):
        _record(outstanding_balance=Decimal("-1.00"))


def test_delinquency_record_rejects_negative_overdue_amount() -> None:
    with pytest.raises(ValidationError):
        _record(overdue_amount=Decimal("-1.00"))


def test_delinquency_record_rejects_negative_dpd() -> None:
    with pytest.raises(ValidationError):
        _record(dpd=-1)


def test_delinquency_record_as_of_may_be_none_for_unknown_freshness() -> None:
    record = _record(as_of=None)
    assert record.as_of is None


def test_delinquency_record_version_starts_at_one() -> None:
    record = _record(record_version=1)
    assert record.record_version == 1


def test_delinquency_record_rejects_version_below_one() -> None:
    with pytest.raises(ValidationError):
        _record(record_version=0)


def test_delinquency_record_bucket_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        _record(bucket="DPD_120_PLUS")
