"""AC3: seed validation rejects inconsistent records (DPD not matching
bucket, negative balance, overdue above balance, item sum mismatch,
vulnerability flag without category) and flags them with a reason instead of
loading silently."""

from __future__ import annotations

from datetime import UTC, date, datetime

from collectai.persistence.seed.models import SeedDataset
from collectai.persistence.seed.validator import validate_seed_dataset
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _valid_record() -> dict[str, object]:
    return {
        "account_id": "acc_000001",
        "customer_id": "cus_000001",
        "outstanding_balance": Money("1000.00"),
        "overdue_amount": Money("100.00"),
        "dpd": 15,
        "bucket": "DPD_1_29",
        "collection_status": "IN_PROGRESS",
        "as_of": _NOW,
        "record_version": 1,
        "updated_at": _NOW,
    }


def _valid_customer() -> dict[str, object]:
    return {
        "customer_id": "cus_000001",
        "display_name": "Avery Nakamura",
        "email": "avery.nakamura@example.com",
        "phone": "+1-555-0142",
        "vulnerability_flag": False,
        "vulnerability_category": None,
        "vulnerability_case_id": None,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _valid_item() -> dict[str, object]:
    return {
        "item_id": "itm_0000010",
        "account_id": "acc_000001",
        "customer_id": "cus_000001",
        "kind": "INSTALLMENT",
        "label": "Installment item 1",
        "amount_outstanding": Money("100.00"),
        "due_date": date(2026, 8, 1),
        "status": "OPEN",
    }


def test_valid_dataset_produces_no_failures() -> None:
    dataset = SeedDataset(
        customers=[_valid_customer()],
        delinquency_records=[_valid_record()],
        delinquent_items=[_valid_item()],
    )
    assert validate_seed_dataset(dataset) == []


def test_dpd_not_matching_bucket_is_rejected_with_reason() -> None:
    record = _valid_record()
    record["dpd"] = 45  # DPD_30_59, but bucket below says DPD_1_29
    dataset = SeedDataset(
        customers=[_valid_customer()],
        delinquency_records=[record],
        delinquent_items=[_valid_item()],
    )

    failures = validate_seed_dataset(dataset)

    assert any(
        f.reason_code is ReasonCode.INCONSISTENT_RECORD and f.entity_id == "acc_000001"
        for f in failures
    )


def test_negative_balance_is_rejected_with_reason() -> None:
    record = _valid_record()
    record["outstanding_balance"] = Money("0")
    record["overdue_amount"] = Money("0")
    # Simulate a negative value directly (Money itself rejects negatives, so
    # the seed validator must catch this even if a future generator bug
    # produced a raw negative Decimal through some other path).
    record["outstanding_balance"] = _NegativeMoneyStub(-50)

    dataset = SeedDataset(customers=[_valid_customer()], delinquency_records=[record])
    failures = validate_seed_dataset(dataset)

    assert any(f.reason_code is ReasonCode.NEGATIVE_AMOUNT for f in failures)


def test_overdue_amount_above_outstanding_balance_is_rejected() -> None:
    record = _valid_record()
    record["outstanding_balance"] = Money("50.00")
    record["overdue_amount"] = Money("100.00")
    dataset = SeedDataset(customers=[_valid_customer()], delinquency_records=[record])

    failures = validate_seed_dataset(dataset)

    assert any(
        f.reason_code is ReasonCode.INCONSISTENT_RECORD and "exceeds" in f.detail for f in failures
    )


def test_item_sum_not_equal_to_overdue_amount_is_rejected() -> None:
    item = _valid_item()
    item["amount_outstanding"] = Money("40.00")  # record's overdue_amount is 100.00
    dataset = SeedDataset(
        customers=[_valid_customer()],
        delinquency_records=[_valid_record()],
        delinquent_items=[item],
    )

    failures = validate_seed_dataset(dataset)

    assert any(
        f.entity == "delinquent_item" and f.reason_code is ReasonCode.INCONSISTENT_RECORD
        for f in failures
    )


def test_vulnerability_flag_without_category_is_rejected() -> None:
    customer = _valid_customer()
    customer["vulnerability_flag"] = True
    customer["vulnerability_category"] = None
    dataset = SeedDataset(customers=[customer])

    failures = validate_seed_dataset(dataset)

    assert any(
        f.entity == "customer" and f.reason_code is ReasonCode.FIELD_INVALID for f in failures
    )


class _NegativeMoneyStub:
    """A minimal stand-in exposing `.amount` like `Money`, used only to
    prove the validator itself rejects a negative amount rather than relying
    on `Money`'s own constructor guard (which the validator must not assume
    is the only path a negative value could take)."""

    def __init__(self, value: int) -> None:
        from decimal import Decimal

        self.amount = Decimal(value)
