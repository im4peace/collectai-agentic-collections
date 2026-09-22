"""Reusable SQLAlchemy `TypeDecorator`s shared by every ORM table module.

`MoneyType` is the single mapping between the application-level `Money` value
type and the `NUMERIC(14,2)` column type (data-models.md section 1: "Money:
NUMERIC(14,2); Python Decimal end to end"). No ORM column stores a bare
`Decimal` or `float`; every money column in `persistence/orm/` uses this type
so the round-trip guarantee (AC2) holds uniformly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from collectai.types.money import Money

_MONEY_PRECISION = 14
_MONEY_SCALE = 2


class MoneyType(TypeDecorator[Money]):
    """Maps `Money` (Decimal-backed) to and from `NUMERIC(14,2)`.

    Bind: a `Money` is unwrapped to its underlying `Decimal` before going to
    the driver. Result: the `Decimal` read back from Postgres is wrapped in a
    `Money` so callers never see a bare `Decimal` from a repository read.
    """

    impl = Numeric(_MONEY_PRECISION, _MONEY_SCALE)
    cache_ok = True

    def process_bind_param(self, value: Money | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, Money):
            raise TypeError(
                f"MoneyType column requires a Money instance, got {type(value).__name__}"
            )
        return value.amount

    def process_result_value(self, value: Any, dialect: Dialect) -> Money | None:
        if value is None:
            return None
        return Money(value)
