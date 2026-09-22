"""Immutable, Decimal-backed money value type.

Every money field in the system is a `Money`, never a bare `Decimal`, `float`
or string. This is the one place float coercion, negative amounts and
over-precision inputs are rejected, with a typed, distinguishable reason code
per failure (api-contracts.md section 1.4).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Final

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from collectai.types.reason_codes import ReasonCode

_TWO_PLACES: Final[Decimal] = Decimal("0.01")
_ZERO: Final[Decimal] = Decimal("0")


class MoneyValidationError(ValueError):
    """Raised when a `Money` value fails validation.

    Carries a typed `ReasonCode` so callers can branch on the failure without
    parsing the message string.
    """

    def __init__(self, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _reject_unsupported_type(amount: object) -> Decimal:
    raise MoneyValidationError(
        ReasonCode.FIELD_INVALID,
        f"Unsupported Money input type: {type(amount).__name__}",
    )


def _coerce_to_decimal(amount: Decimal | int | str) -> Decimal:
    if isinstance(amount, bool):
        return _reject_unsupported_type(amount)
    if isinstance(amount, float):
        raise MoneyValidationError(
            ReasonCode.FLOAT_NOT_ALLOWED,
            "Money does not accept float input; pass a Decimal, int, or numeric string.",
        )
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, int):
        return Decimal(amount)
    if isinstance(amount, str):
        try:
            return Decimal(amount)
        except InvalidOperation as exc:
            raise MoneyValidationError(
                ReasonCode.FIELD_INVALID,
                f"Money string is not a valid decimal amount: {amount!r}",
            ) from exc
    return _reject_unsupported_type(amount)


def _validate_amount(decimal_amount: Decimal) -> Decimal:
    if not decimal_amount.is_finite():
        raise MoneyValidationError(
            ReasonCode.FIELD_INVALID, "Money amount must be a finite value."
        )
    if decimal_amount < _ZERO:
        raise MoneyValidationError(
            ReasonCode.NEGATIVE_AMOUNT,
            f"Money amount must not be negative: {decimal_amount}",
        )
    exponent = decimal_amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise MoneyValidationError(
            ReasonCode.OVER_PRECISION,
            f"Money amount must have at most 2 decimal places: {decimal_amount}",
        )
    return decimal_amount


class Money:
    """An immutable, non-negative monetary amount backed by `decimal.Decimal`."""

    __slots__ = ("_amount",)

    def __init__(self, amount: Decimal | int | str) -> None:
        self._amount = _validate_amount(_coerce_to_decimal(amount))

    @classmethod
    def from_string(cls, value: str) -> Money:
        """Parse an API/JSON money string (e.g. "1250.50") into a `Money`."""
        return cls(value)

    @property
    def amount(self) -> Decimal:
        return self._amount

    def to_api_string(self) -> str:
        """Serialize as a fixed 2-decimal-place string, e.g. "1250.50"."""
        quantized = self._amount.quantize(_TWO_PLACES)
        return format(quantized, "f")

    def __str__(self) -> str:
        return self.to_api_string()

    def __repr__(self) -> str:
        return f"Money('{self.to_api_string()}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self._amount == other._amount

    def __hash__(self) -> int:
        return hash(self._amount)

    def __lt__(self, other: Money) -> bool:
        self._require_money(other)
        return self._amount < other._amount

    def __le__(self, other: Money) -> bool:
        self._require_money(other)
        return self._amount <= other._amount

    def __gt__(self, other: Money) -> bool:
        self._require_money(other)
        return self._amount > other._amount

    def __ge__(self, other: Money) -> bool:
        self._require_money(other)
        return self._amount >= other._amount

    def __add__(self, other: Money) -> Money:
        self._require_money(other)
        return Money(self._amount + other._amount)

    def __sub__(self, other: Money) -> Money:
        self._require_money(other)
        return Money(self._amount - other._amount)

    @staticmethod
    def _require_money(other: object) -> None:
        if not isinstance(other, Money):
            raise TypeError(
                f"Money can only be compared or combined with Money, got {type(other).__name__}"
            )

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate_for_pydantic,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda money: money.to_api_string(),
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def _validate_for_pydantic(cls, value: object) -> Money:
        if isinstance(value, Money):
            return value
        if isinstance(value, Decimal | int | str) and not isinstance(value, bool):
            return cls(value)
        raise MoneyValidationError(
            ReasonCode.FIELD_INVALID,
            "Money must be a Money instance, Decimal, int, or numeric string, "
            f"got {type(value).__name__}",
        )
