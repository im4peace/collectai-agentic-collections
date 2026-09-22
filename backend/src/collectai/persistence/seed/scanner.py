"""Prohibited-pattern scan over generated seed data (data-models.md section 6,
AC4). Confirms zero real-looking PII: emails only on example.com, phones only
in the fictional +1-555-01xx range, no 13-19 digit sequences anywhere in a
generated string field (catches anything that looks like a card number), and
no SSN-shaped or CVV/PIN-labelled patterns.
"""

from __future__ import annotations

import re
from typing import Any

from collectai.persistence.seed.models import SeedDataset, SeedValidationFailure
from collectai.types.reason_codes import ReasonCode

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@example\.com$")
_PHONE_PATTERN = re.compile(r"^\+1-555-01\d{2}$")
_CARD_LIKE_DIGIT_RUN = re.compile(r"\d{13,19}")
_SSN_SHAPED = re.compile(r"\d{3}-\d{2}-\d{4}")
_CVV_OR_PIN_LABELLED = re.compile(r"\b(CVV|PIN)\b\s*[:=]?\s*\d{3,4}\b", re.IGNORECASE)


def scan_seed_dataset(dataset: SeedDataset) -> list[SeedValidationFailure]:
    """Return every prohibited-pattern finding in `dataset`. An empty list
    means the dataset contains no real-looking PII."""
    findings: list[SeedValidationFailure] = []
    findings.extend(_scan_customer_contact_fields(dataset.customers))
    for table_name, rows in (
        ("customer", dataset.customers),
        ("account", dataset.accounts),
        ("delinquency_record", dataset.delinquency_records),
        ("delinquent_item", dataset.delinquent_items),
        ("interaction", dataset.interactions),
        ("promise_to_pay", dataset.promise_to_pays),
    ):
        findings.extend(_scan_rows_for_dangerous_patterns(table_name, rows))
    return findings


def _scan_customer_contact_fields(customers: list[dict[str, Any]]) -> list[SeedValidationFailure]:
    findings: list[SeedValidationFailure] = []
    for customer in customers:
        email = customer["email"]
        if not _EMAIL_PATTERN.match(email):
            findings.append(
                _finding("customer", customer["customer_id"], f"email not on example.com: {email}")
            )
        phone = customer["phone"]
        if not _PHONE_PATTERN.match(phone):
            findings.append(
                _finding(
                    "customer",
                    customer["customer_id"],
                    f"phone outside the +1-555-01xx fictional range: {phone}",
                )
            )
    return findings


def _scan_rows_for_dangerous_patterns(
    table_name: str, rows: list[dict[str, Any]]
) -> list[SeedValidationFailure]:
    findings: list[SeedValidationFailure] = []
    for row in rows:
        entity_id = _row_identifier(row)
        for text_value in _iter_string_values(row):
            findings.extend(_check_text_for_dangerous_patterns(table_name, entity_id, text_value))
    return findings


def _check_text_for_dangerous_patterns(
    table_name: str, entity_id: str, text_value: str
) -> list[SeedValidationFailure]:
    findings: list[SeedValidationFailure] = []
    if _CARD_LIKE_DIGIT_RUN.search(text_value):
        findings.append(
            _finding(table_name, entity_id, f"13-19 digit sequence found: {text_value!r}")
        )
    if _SSN_SHAPED.search(text_value):
        findings.append(
            _finding(table_name, entity_id, f"SSN-shaped pattern found: {text_value!r}")
        )
    if _CVV_OR_PIN_LABELLED.search(text_value):
        findings.append(
            _finding(table_name, entity_id, f"CVV/PIN-labelled pattern found: {text_value!r}")
        )
    return findings


def _row_identifier(row: dict[str, Any]) -> str:
    for key in row:
        if key.endswith("_id"):
            return str(row[key])
    return "<unknown>"


def _iter_string_values(value: Any) -> list[str]:  # noqa: ANN401 - recursive walk over untyped JSON-ish data
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for nested in value.values():
            found.extend(_iter_string_values(nested))
        return found
    if isinstance(value, list):
        found = []
        for nested in value:
            found.extend(_iter_string_values(nested))
        return found
    return []


def _finding(entity: str, entity_id: str, detail: str) -> SeedValidationFailure:
    return SeedValidationFailure(
        reason_code=ReasonCode.FIELD_INVALID, entity=entity, entity_id=entity_id, detail=detail
    )
