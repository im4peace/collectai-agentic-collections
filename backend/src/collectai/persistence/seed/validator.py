"""Seed data validation (data-models.md section 6, AC3).

Rejects and reports inconsistent records with a typed reason instead of
loading them silently: DPD not matching bucket, negative balance, overdue
amount above outstanding balance, item sum not equal to overdue amount,
and vulnerability flag set without a category.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from collectai.persistence.seed.builders import bucket_for_dpd
from collectai.persistence.seed.models import SeedDataset, SeedValidationFailure
from collectai.types.reason_codes import ReasonCode


def validate_seed_dataset(dataset: SeedDataset) -> list[SeedValidationFailure]:
    """Return every validation failure found in `dataset`. An empty list
    means every record may be loaded as-is."""
    failures: list[SeedValidationFailure] = []
    failures.extend(_validate_customers(dataset.customers))
    failures.extend(_validate_delinquency_records(dataset.delinquency_records))
    failures.extend(_validate_item_sums(dataset.delinquency_records, dataset.delinquent_items))
    return failures


def _validate_customers(customers: list[dict[str, Any]]) -> list[SeedValidationFailure]:
    failures: list[SeedValidationFailure] = []
    for customer in customers:
        if customer["vulnerability_flag"] and customer["vulnerability_category"] is None:
            failures.append(
                SeedValidationFailure(
                    reason_code=ReasonCode.FIELD_INVALID,
                    entity="customer",
                    entity_id=customer["customer_id"],
                    detail="vulnerability_flag is true but vulnerability_category is null",
                )
            )
    return failures


def _validate_delinquency_records(
    records: list[dict[str, Any]],
) -> list[SeedValidationFailure]:
    failures: list[SeedValidationFailure] = []
    for record in records:
        failures.extend(_validate_one_delinquency_record(record))
    return failures


def _validate_one_delinquency_record(record: dict[str, Any]) -> list[SeedValidationFailure]:
    failures: list[SeedValidationFailure] = []
    account_id = record["account_id"]
    outstanding_balance: Decimal = record["outstanding_balance"].amount
    overdue_amount: Decimal = record["overdue_amount"].amount
    dpd: int = record["dpd"]
    bucket: str = record["bucket"]

    if outstanding_balance < 0 or overdue_amount < 0:
        failures.append(
            SeedValidationFailure(
                reason_code=ReasonCode.NEGATIVE_AMOUNT,
                entity="delinquency_record",
                entity_id=account_id,
                detail=(
                    f"negative balance: outstanding={outstanding_balance}, "
                    f"overdue={overdue_amount}"
                ),
            )
        )
    if bucket_for_dpd(dpd) != bucket:
        failures.append(
            SeedValidationFailure(
                reason_code=ReasonCode.INCONSISTENT_RECORD,
                entity="delinquency_record",
                entity_id=account_id,
                detail=f"dpd={dpd} does not match bucket={bucket}",
            )
        )
    if overdue_amount > outstanding_balance:
        failures.append(
            SeedValidationFailure(
                reason_code=ReasonCode.INCONSISTENT_RECORD,
                entity="delinquency_record",
                entity_id=account_id,
                detail=(
                    f"overdue_amount={overdue_amount} "
                    f"exceeds outstanding_balance={outstanding_balance}"
                ),
            )
        )
    return failures


def _validate_item_sums(
    records: list[dict[str, Any]], items: list[dict[str, Any]]
) -> list[SeedValidationFailure]:
    items_by_account: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in items:
        if item["status"] == "OPEN":
            items_by_account[item["account_id"]] += item["amount_outstanding"].amount

    failures: list[SeedValidationFailure] = []
    for record in records:
        account_id = record["account_id"]
        overdue_amount: Decimal = record["overdue_amount"].amount
        item_sum = items_by_account.get(account_id, Decimal("0"))
        if item_sum != overdue_amount:
            failures.append(
                SeedValidationFailure(
                    reason_code=ReasonCode.INCONSISTENT_RECORD,
                    entity="delinquent_item",
                    entity_id=account_id,
                    detail=(
                        f"open item sum={item_sum} "
                        f"does not equal overdue_amount={overdue_amount}"
                    ),
                )
            )
    return failures
