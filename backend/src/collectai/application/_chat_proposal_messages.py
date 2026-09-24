"""Customer-facing copy for the chat proposal flow (E6-S2, E6-S3), split out
of `_chat_proposal_flow.py` to keep that module under the code-gen skill's
300-line block threshold. Every string here is a template
(`content_source=TEMPLATE`), never model-generated prose -- same rule
`_chat_templates.py` documents for the rest of the chat flow.
"""

from __future__ import annotations

from datetime import date

from collectai.rules_engine.payable import PayableOption
from collectai.rules_engine.ptp_rules import Alternatives
from collectai.types.enums import PayableOptionType
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

SUPPRESSED_MESSAGE = (
    "Your account is currently being reviewed by a specialist, so I can't set up a new "
    "payment or promise here right now. You can talk to a human at any time."
)

NO_PAYABLE_OPTIONS_MESSAGE = (
    "There isn't a payment option available for this account right now. "
    "You can talk to a human at any time."
)

_PTP_REJECTION_REASONS: dict[ReasonCode, str] = {
    ReasonCode.ZERO_AMOUNT: "the amount must be greater than zero",
    ReasonCode.NEGATIVE_AMOUNT: "the amount must not be negative",
    ReasonCode.OVER_PRECISION: "the amount can have at most 2 decimal places",
    ReasonCode.FLOAT_NOT_ALLOWED: "the amount must be a plain number",
    ReasonCode.OVER_BALANCE: "the amount is more than the current overdue amount",
    ReasonCode.BELOW_MIN_AMOUNT: "the amount is below the minimum we can accept",
    ReasonCode.PAST_DATE: "the date must not be in the past",
    ReasonCode.OUTSIDE_WINDOW: "the date is too far in the future",
    ReasonCode.FIELD_INVALID: "the amount isn't a valid number",
}


def ptp_offer_message(*, promised_amount: Money, promised_date: date) -> str:
    return (
        f"You can promise {promised_amount.to_api_string()} by {promised_date.isoformat()}. "
        "Please confirm below."
    )


def ptp_rejection_message(*, reason_code: ReasonCode, alternatives: Alternatives | None) -> str:
    reason_text = _PTP_REJECTION_REASONS.get(reason_code, "that amount or date isn't valid")
    parts = [f"I can't set that up because {reason_text}."]
    if alternatives is not None and alternatives.valid_amount_range is not None:
        amount_range = alternatives.valid_amount_range
        parts.append(
            f"You can promise between {amount_range.min.to_api_string()} and "
            f"{amount_range.max.to_api_string()}."
        )
    if alternatives is not None and alternatives.valid_date_range is not None:
        date_range = alternatives.valid_date_range
        parts.append(
            f"The date must be between {date_range.earliest.isoformat()} and "
            f"{date_range.latest.isoformat()}."
        )
    return " ".join(parts)


def ptp_clarification_message(*, min_amount: Money, overdue_amount: Money, window_end: date) -> str:
    return (
        "To set up a promise to pay, please tell me the amount and date you'd like to "
        f"promise -- for example, an amount between {min_amount.to_api_string()} and "
        f"{overdue_amount.to_api_string()}, by {window_end.isoformat()}."
    )


def payment_offer_message(*, amount: Money) -> str:
    return (
        f"You can pay {amount.to_api_string()} now. This is a simulated payment -- "
        "no real money moves. Please confirm below."
    )


def payment_choice_message(options: list[PayableOption]) -> str:
    described = [
        f"{option.amount.to_api_string()} ({_option_label(option.option_type)})"
        for option in options
    ]
    joined = " or ".join(described)
    return (
        f"You can pay {joined} now -- this would be a simulated payment. "
        "Which would you like?"
    )


def _option_label(option_type: PayableOptionType) -> str:
    return "the overdue amount" if option_type is PayableOptionType.OVERDUE_AMOUNT else (
        "the full balance"
    )
