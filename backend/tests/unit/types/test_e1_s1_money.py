"""Tests for the Decimal-backed Money value type (E1-S1 AC1, AC2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from collectai.types.money import Money, MoneyValidationError
from collectai.types.reason_codes import ReasonCode


def test_money_wraps_a_decimal_amount() -> None:
    money = Money(Decimal("1250.50"))
    assert money.amount == Decimal("1250.50")


def test_money_accepts_int_and_numeric_string_construction() -> None:
    assert Money(10).amount == Decimal("10")
    assert Money("1250.50").amount == Decimal("1250.50")


def test_money_rejects_float_input_with_typed_error() -> None:
    with pytest.raises(MoneyValidationError) as excinfo:
        Money(1250.50)  # type: ignore[arg-type]
    assert excinfo.value.reason_code is ReasonCode.FLOAT_NOT_ALLOWED


def test_money_rejects_negative_values_with_negative_amount_reason_code() -> None:
    with pytest.raises(MoneyValidationError) as excinfo:
        Money(Decimal("-1.00"))
    assert excinfo.value.reason_code is ReasonCode.NEGATIVE_AMOUNT


def test_money_rejects_more_than_two_decimal_places_with_over_precision_reason_code() -> None:
    with pytest.raises(MoneyValidationError) as excinfo:
        Money(Decimal("10.505"))
    assert excinfo.value.reason_code is ReasonCode.OVER_PRECISION


def test_negative_amount_and_over_precision_are_distinct_reason_codes() -> None:
    assert ReasonCode.NEGATIVE_AMOUNT is not ReasonCode.OVER_PRECISION


def test_money_allows_zero_and_up_to_two_decimal_places() -> None:
    assert Money(Decimal("0")).amount == Decimal("0")
    assert Money(Decimal("10")).amount == Decimal("10")
    assert Money(Decimal("10.5")).amount == Decimal("10.5")
    assert Money(Decimal("10.50")).amount == Decimal("10.50")


def test_to_api_string_emits_fixed_two_decimal_place_strings() -> None:
    assert Money(Decimal("1250.50")).to_api_string() == "1250.50"
    assert Money(Decimal("1250.5")).to_api_string() == "1250.50"
    assert Money(Decimal("1250")).to_api_string() == "1250.00"
    assert Money(Decimal("0")).to_api_string() == "0.00"


def test_str_uses_the_api_string_form() -> None:
    assert str(Money(Decimal("1250.50"))) == "1250.50"


def test_from_string_parses_api_json_string_input() -> None:
    money = Money.from_string("1250.50")
    assert money == Money(Decimal("1250.50"))


def test_from_string_rejects_invalid_numeric_strings() -> None:
    with pytest.raises(MoneyValidationError) as excinfo:
        Money.from_string("not-a-number")
    assert excinfo.value.reason_code is ReasonCode.FIELD_INVALID


def test_money_equality_and_hash_are_value_based() -> None:
    assert Money(Decimal("10.00")) == Money(Decimal("10"))
    assert hash(Money(Decimal("10.00"))) == hash(Money(Decimal("10")))
    assert Money(Decimal("10.00")) != Money(Decimal("10.01"))


def test_money_ordering() -> None:
    assert Money(Decimal("5.00")) < Money(Decimal("10.00"))
    assert Money(Decimal("10.00")) > Money(Decimal("5.00"))
    assert Money(Decimal("10.00")) >= Money(Decimal("10.00"))
    assert Money(Decimal("10.00")) <= Money(Decimal("10.00"))


def test_money_addition_and_subtraction() -> None:
    assert Money(Decimal("5.00")) + Money(Decimal("2.50")) == Money(Decimal("7.50"))
    assert Money(Decimal("5.00")) - Money(Decimal("2.50")) == Money(Decimal("2.50"))


def test_money_subtraction_below_zero_raises_negative_amount() -> None:
    with pytest.raises(MoneyValidationError) as excinfo:
        Money(Decimal("2.00")) - Money(Decimal("5.00"))
    assert excinfo.value.reason_code is ReasonCode.NEGATIVE_AMOUNT


def test_money_repr_is_useful_for_debugging() -> None:
    assert repr(Money(Decimal("10.00"))) == "Money('10.00')"


class _Wallet(BaseModel):
    balance: Money


def test_money_works_as_a_pydantic_field_type_validating_from_string() -> None:
    wallet = _Wallet.model_validate({"balance": "42.10"})
    assert wallet.balance == Money(Decimal("42.10"))


def test_money_as_pydantic_field_serializes_to_api_string() -> None:
    wallet = _Wallet(balance=Money(Decimal("42.10")))
    assert wallet.model_dump(mode="json") == {"balance": "42.10"}


def test_money_as_pydantic_field_rejects_negative_string() -> None:
    with pytest.raises(ValidationError):
        _Wallet.model_validate({"balance": "-5.00"})
