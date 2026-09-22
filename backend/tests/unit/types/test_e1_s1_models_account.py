"""Tests for the Account domain model (data-models.md Account)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from collectai.types.enums import AccountType
from collectai.types.models import Account, CardProductAttributes, PersonalLoanProductAttributes


def _card_account(**overrides: object) -> Account:
    fields: dict[str, object] = {
        "account_id": "acc_000123",
        "customer_id": "cus_000101",
        "account_type": AccountType.CARD,
        "product_name": "Everyday Rewards Card",
        "currency": "USD",
        "opened_on": date(2025, 3, 14),
        "product_attributes": CardProductAttributes(
            credit_limit=Decimal("5000.00"), minimum_payment_due=Decimal("125.00")
        ),
        "created_at": datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return Account.model_validate(fields)


def test_account_accepts_card_type_with_card_attributes() -> None:
    account = _card_account()
    assert account.account_type is AccountType.CARD
    assert isinstance(account.product_attributes, CardProductAttributes)
    assert account.product_attributes.credit_limit.amount == Decimal("5000.00")


def test_account_accepts_personal_loan_type_with_loan_attributes() -> None:
    account = _card_account(
        account_type=AccountType.PERSONAL_LOAN,
        product_name="Everyday Personal Loan",
        product_attributes=PersonalLoanProductAttributes(
            original_principal=Decimal("12000.00"),
            term_months=36,
            monthly_installment=Decimal("385.20"),
        ),
    )
    assert account.account_type is AccountType.PERSONAL_LOAN
    assert isinstance(account.product_attributes, PersonalLoanProductAttributes)
    assert account.product_attributes.term_months == 36


def test_account_type_rejects_any_value_outside_card_or_personal_loan() -> None:
    with pytest.raises(ValidationError):
        _card_account(account_type="SAVINGS")


def test_account_rejects_card_type_with_personal_loan_attributes() -> None:
    with pytest.raises(ValidationError):
        _card_account(
            product_attributes=PersonalLoanProductAttributes(
                original_principal=Decimal("12000.00"),
                term_months=36,
                monthly_installment=Decimal("385.20"),
            )
        )


def test_account_rejects_personal_loan_type_with_card_attributes() -> None:
    with pytest.raises(ValidationError):
        _card_account(
            account_type=AccountType.PERSONAL_LOAN,
            product_attributes=CardProductAttributes(
                credit_limit=Decimal("5000.00"), minimum_payment_due=Decimal("125.00")
            ),
        )


def test_account_currency_is_always_usd() -> None:
    with pytest.raises(ValidationError):
        _card_account(currency="EUR")


def test_account_id_and_customer_id_must_match_their_prefixes() -> None:
    with pytest.raises(ValidationError):
        _card_account(account_id="cus_000123")
    with pytest.raises(ValidationError):
        _card_account(customer_id="acc_000101")


def test_account_model_is_frozen() -> None:
    account = _card_account()
    with pytest.raises(ValidationError):
        account.product_name = "Renamed Product"  # type: ignore[misc]
