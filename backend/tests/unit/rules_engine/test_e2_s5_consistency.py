"""Tests for `check_consistency` (E2-S5 AC4).

Negative overdue_amount is deliberately NOT exercised here: `Money.__init__`
unconditionally rejects a negative `Decimal`/`int`/`str` input with
`MoneyValidationError(NEGATIVE_AMOUNT)` (collectai/types/money.py), so a
`DelinquencyRecord` can never legitimately hold a negative `overdue_amount`
through any public construction path. `check_consistency`'s negative-amount
branch is defence-in-depth per AC4's literal wording ("negative balance"),
but there is no non-contrived way to reach it in a test without bypassing
`Money`'s own guarantees (e.g. via `object.__new__`), which would test an
implementation detail rather than real behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

from collectai.rules_engine.consistency import check_consistency
from collectai.types.enums import Bucket, CollectionStatus
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_OVERDUE_AMOUNT = Money("770.40")
_OUTSTANDING_BALANCE = Money("8420.10")


def _record(
    *,
    dpd: int = 34,
    bucket: Bucket = Bucket.DPD_30_59,
    overdue_amount: Money = _OVERDUE_AMOUNT,
    outstanding_balance: Money = _OUTSTANDING_BALANCE,
) -> DelinquencyRecord:
    return DelinquencyRecord(
        account_id="acc_000123",
        customer_id="cus_000101",
        outstanding_balance=outstanding_balance,
        overdue_amount=overdue_amount,
        dpd=dpd,
        bucket=bucket,
        collection_status=CollectionStatus.IN_PROGRESS,
        as_of=_NOW,
        record_version=7,
        updated_at=_NOW,
    )


def test_consistent_record_passes_with_no_reason_code() -> None:
    result = check_consistency(_record())

    assert result.consistent is True
    assert result.reason_code is None


def test_bucket_not_matching_dpd_is_inconsistent() -> None:
    """AC4: dpd=34 belongs in DPD_30_59, not DPD_1_29."""
    result = check_consistency(_record(dpd=34, bucket=Bucket.DPD_1_29))

    assert result.consistent is False
    assert result.reason_code is ReasonCode.INCONSISTENT_RECORD
    assert "bucket_does_not_match_dpd" in result.violations


def test_dpd_zero_must_be_current_bucket() -> None:
    result = check_consistency(_record(dpd=0, bucket=Bucket.DPD_1_29))

    assert result.consistent is False
    assert result.reason_code is ReasonCode.INCONSISTENT_RECORD


def test_dpd_ninety_plus_must_be_dpd_90_plus_bucket() -> None:
    result = check_consistency(_record(dpd=120, bucket=Bucket.DPD_60_89))

    assert result.consistent is False
    assert result.reason_code is ReasonCode.INCONSISTENT_RECORD


def test_overdue_amount_above_outstanding_balance_is_inconsistent() -> None:
    """AC4: overdue_amount must never exceed outstanding_balance."""
    result = check_consistency(
        _record(overdue_amount=Money("9000.00"), outstanding_balance=Money("8420.10"))
    )

    assert result.consistent is False
    assert result.reason_code is ReasonCode.INCONSISTENT_RECORD
    assert "overdue_amount_exceeds_outstanding_balance" in result.violations


def test_overdue_amount_equal_to_outstanding_balance_is_consistent() -> None:
    """Boundary: overdue_amount == outstanding_balance is allowed (fully overdue)."""
    result = check_consistency(
        _record(overdue_amount=Money("8420.10"), outstanding_balance=Money("8420.10"))
    )

    assert result.consistent is True
    assert result.reason_code is None


def test_multiple_violations_still_reports_single_flat_inconsistent_record_code() -> None:
    """The RecordCheck schema is boolean + one reason code, not a list of
    per-violation codes, even when multiple checks fail at once."""
    result = check_consistency(
        _record(dpd=34, bucket=Bucket.CURRENT, overdue_amount=Money("9000.00"))
    )

    assert result.consistent is False
    assert result.reason_code is ReasonCode.INCONSISTENT_RECORD
    assert len(result.violations) >= 2
