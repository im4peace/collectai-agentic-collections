"""Exact-sum installment schedule math (E2-S3 AC1).

Kept as its own module (learned-rules.md Rule 3): the no-rounding-loss
guarantee is a self-contained piece of arithmetic, easiest to reason about
and test in isolation from eligibility classification. Every division here
is by a policy-sourced `installment_counts` value, which `ArrangementParameters`
(config/policy/models.py) validates as non-empty with every count in
`[2, 60]` — so this module can never divide by zero for valid policy input.

All money math is done in `Decimal`, quantized to whole cents, before any
`Money` is constructed (`Money` rejects more than 2 decimal places).
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal

from collectai.config.policy.models import ArrangementParameters
from collectai.rules_engine.arrangement._types import ArrangementOption, ScheduleEntry
from collectai.types.money import Money

_TWO_PLACES = Decimal("0.01")
_FREQUENCY_MONTHLY = "MONTHLY"


def quantize_down(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_DOWN)


def regular_and_final_installment(total: Decimal, count: int) -> tuple[Decimal, Decimal]:
    """Split `total` into `count` cents-exact installments with no remainder.

    `regular` is `total / count` quantized down to whole cents; `final`
    absorbs whatever is left so `regular * (count - 1) + final == total`
    exactly (data-models.md `PaymentArrangement` service invariant).
    """
    regular = quantize_down(total / count)
    final = total - regular * (count - 1)
    return regular, final


def expected_regular_installment(total: Decimal, count: int) -> Decimal | None:
    """Same math as `regular_and_final_installment`, guarded for `count < 1`.

    Used against a *requested* installment count, which — unlike a
    policy-sourced count — is not guaranteed to be positive.
    """
    if count < 1:
        return None
    regular, _ = regular_and_final_installment(total, count)
    return regular


def add_months(start: date, months: int) -> date:
    """Add whole calendar months to `start`, clamping into short months."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day_of_month))


def build_schedule(
    count: int, first_date: date, regular: Money, final: Money
) -> list[ScheduleEntry]:
    entries: list[ScheduleEntry] = []
    for index in range(count):
        amount = final if index == count - 1 else regular
        entries.append(
            ScheduleEntry(
                sequence=index + 1,
                due_date=add_months(first_date, index),
                amount=amount,
            )
        )
    return entries


def build_option(count: int, overdue_amount: Money, first_date: date) -> ArrangementOption:
    regular_decimal, final_decimal = regular_and_final_installment(overdue_amount.amount, count)
    regular = Money(regular_decimal)
    final = Money(final_decimal)
    return ArrangementOption(
        option_id=f"opt-{count}-{first_date.isoformat()}",
        installment_count=count,
        installment_amount=regular,
        final_installment_amount=final,
        total_amount=overdue_amount,
        first_installment_date=first_date,
        frequency=_FREQUENCY_MONTHLY,
        schedule=build_schedule(count, first_date, regular, final),
    )


def build_eligible_options(
    arrangement: ArrangementParameters, overdue_amount: Money, first_date: date
) -> list[ArrangementOption]:
    """One `ArrangementOption` per policy `installment_counts` value.

    A count whose regular installment falls below
    `arrangement.min_installment_amount` is silently excluded (fewer options
    offered), never a hard eligibility failure by itself.
    """
    options: list[ArrangementOption] = []
    for count in arrangement.installment_counts:
        option = build_option(count, overdue_amount, first_date)
        if option.installment_amount < arrangement.min_installment_amount:
            continue
        options.append(option)
    return options
