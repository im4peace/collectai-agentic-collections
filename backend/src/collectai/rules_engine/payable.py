"""Deterministic payable amounts for the PAY_NOW flow (E2-S2 AC4).

Suppression is resolved elsewhere (E2-S4); this module accepts the outcome
as a plain `is_suppressed` boolean rather than computing it itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectai.config.policy.models import PolicyRuleSet
from collectai.types.enums import PayableOptionType
from collectai.types.money import Money


@dataclass(frozen=True, slots=True)
class PayableOption:
    option_type: PayableOptionType
    amount: Money


def get_payable_options(
    overdue_amount: Money,
    outstanding_balance: Money,
    is_suppressed: bool,
    policy: PolicyRuleSet,
) -> list[PayableOption]:
    """One `PayableOption` per `PayableOptionType` enabled in policy.

    Returns an empty list when `is_suppressed` is true, regardless of which
    option types the policy enables.
    """
    if is_suppressed:
        return []

    amount_by_type = {
        PayableOptionType.OVERDUE_AMOUNT: overdue_amount,
        PayableOptionType.FULL_BALANCE: outstanding_balance,
    }
    return [
        PayableOption(option_type=option_type, amount=amount_by_type[option_type])
        for option_type in policy.parameters.payment.payable_options
    ]
