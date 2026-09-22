"""AC4: prohibited-pattern scan over seed data finds zero real-looking PII:
emails only on example.com, phones only in the fictional range, no 13-19
digit card-number-like sequences, no CVV/PIN/government-id patterns."""

from __future__ import annotations

from datetime import UTC, datetime

from collectai.persistence.seed.generator import generate_seed_dataset
from collectai.persistence.seed.models import SeedDataset
from collectai.persistence.seed.scanner import scan_seed_dataset

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _base_customer(**overrides: object) -> dict[str, object]:
    customer: dict[str, object] = {
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
    customer.update(overrides)
    return customer


def test_generated_dataset_has_zero_prohibited_pattern_findings() -> None:
    """The scan runs over the actual generated dataset, not just the
    scanner's own unit-level fixtures."""
    dataset = generate_seed_dataset(account_count=250)

    findings = scan_seed_dataset(dataset)

    assert findings == []


def test_scanner_flags_a_non_example_com_email() -> None:
    dataset = SeedDataset(customers=[_base_customer(email="avery.nakamura@realbank.com")])

    findings = scan_seed_dataset(dataset)

    assert any("email" in f.detail for f in findings)


def test_scanner_flags_a_phone_outside_the_fictional_range() -> None:
    dataset = SeedDataset(customers=[_base_customer(phone="+1-212-555-0199")])

    findings = scan_seed_dataset(dataset)

    assert any("phone" in f.detail for f in findings)


def test_scanner_flags_a_card_number_shaped_digit_run() -> None:
    dataset = SeedDataset(customers=[_base_customer(display_name="4111111111111111")])

    findings = scan_seed_dataset(dataset)

    assert any("digit sequence" in f.detail for f in findings)


def test_scanner_flags_an_ssn_shaped_pattern() -> None:
    dataset = SeedDataset(customers=[_base_customer(display_name="123-45-6789")])

    findings = scan_seed_dataset(dataset)

    assert any("SSN-shaped" in f.detail for f in findings)


def test_scanner_flags_a_cvv_labelled_pattern() -> None:
    dataset = SeedDataset(customers=[_base_customer(display_name="CVV: 123")])

    findings = scan_seed_dataset(dataset)

    assert any("CVV/PIN" in f.detail for f in findings)
