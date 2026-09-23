"""E5-S4 AC1, AC2, AC4, AC5: pure Pydantic schema validation for the six
tool argument models and the `EligibleOptionsResult.arrangement_options`
Slice-1 default. No I/O anywhere in this file.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from collectai.ai_orchestration.schemas.tool_args import (
    EscalateToHumanArgs,
    FlagDisputeArgs,
    FlagHardshipArgs,
    GetAccountContextArgs,
    GetEligibleOptionsArgs,
    ProposePtpArgs,
)
from collectai.ai_orchestration.schemas.tool_results import (
    EligibleOptionsResult,
    PtpDateWindowResult,
)
from collectai.types.enums import DisputeCategory, EscalationReason, HardshipIndicatorType

_ACCOUNT_ID = "acc_000101"


def test_get_account_context_args_accepts_a_well_formed_account_id() -> None:
    args = GetAccountContextArgs.model_validate({"account_id": _ACCOUNT_ID})
    assert args.account_id == _ACCOUNT_ID


def test_get_account_context_args_rejects_malformed_account_id() -> None:
    with pytest.raises(ValidationError):
        GetAccountContextArgs.model_validate({"account_id": "not-an-id"})


def test_get_account_context_args_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GetAccountContextArgs.model_validate({"account_id": _ACCOUNT_ID, "extra": "nope"})


def test_get_account_context_args_rejects_missing_account_id() -> None:
    with pytest.raises(ValidationError):
        GetAccountContextArgs.model_validate({})


def test_get_eligible_options_args_accepts_a_well_formed_account_id() -> None:
    args = GetEligibleOptionsArgs.model_validate({"account_id": _ACCOUNT_ID})
    assert args.account_id == _ACCOUNT_ID


def test_propose_ptp_args_accepts_valid_shape() -> None:
    args = ProposePtpArgs.model_validate(
        {"account_id": _ACCOUNT_ID, "promised_amount": "250.00", "promised_date": "2026-10-15"}
    )
    assert args.promised_amount == "250.00"
    assert args.promised_date == date(2026, 10, 15)


def test_propose_ptp_args_rejects_missing_promised_date() -> None:
    with pytest.raises(ValidationError):
        ProposePtpArgs.model_validate({"account_id": _ACCOUNT_ID, "promised_amount": "250.00"})


def test_propose_ptp_args_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ProposePtpArgs.model_validate(
            {
                "account_id": _ACCOUNT_ID,
                "promised_amount": "250.00",
                "promised_date": "2026-10-15",
                "destination": "COLLECTIONS_REVIEW",
            }
        )


def test_flag_hardship_args_accepts_valid_shape() -> None:
    args = FlagHardshipArgs.model_validate(
        {
            "account_id": _ACCOUNT_ID,
            "indicator_type": "JOB_LOSS",
            "note": "Customer reports job loss.",
        }
    )
    assert args.indicator_type is HardshipIndicatorType.JOB_LOSS


def test_flag_hardship_args_rejects_invalid_indicator_type() -> None:
    with pytest.raises(ValidationError):
        FlagHardshipArgs.model_validate(
            {"account_id": _ACCOUNT_ID, "indicator_type": "NOT_A_REAL_INDICATOR", "note": "x"}
        )


def test_flag_hardship_args_rejects_empty_note() -> None:
    with pytest.raises(ValidationError):
        FlagHardshipArgs.model_validate(
            {"account_id": _ACCOUNT_ID, "indicator_type": "JOB_LOSS", "note": ""}
        )


def test_flag_dispute_args_accepts_valid_shape_with_item_id() -> None:
    args = FlagDisputeArgs.model_validate(
        {
            "account_id": _ACCOUNT_ID,
            "category": "AMOUNT_INCORRECT",
            "customer_reason": "The installment amount looks wrong.",
            "item_id": "itm_000771",
        }
    )
    assert args.category is DisputeCategory.AMOUNT_INCORRECT
    assert args.item_id == "itm_000771"


def test_flag_dispute_args_accepts_valid_shape_without_item_id() -> None:
    args = FlagDisputeArgs.model_validate(
        {
            "account_id": _ACCOUNT_ID,
            "category": "NOT_MY_DEBT",
            "customer_reason": "This is not my account.",
        }
    )
    assert args.item_id is None


def test_flag_dispute_args_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        FlagDisputeArgs.model_validate(
            {"account_id": _ACCOUNT_ID, "category": "NOT_A_CATEGORY", "customer_reason": "x"}
        )


def test_escalate_to_human_args_accepts_reason_and_rationale_only() -> None:
    args = EscalateToHumanArgs.model_validate(
        {"reason": "FINANCIAL_HARDSHIP", "rationale": "Customer reports job loss."}
    )
    assert args.reason is EscalationReason.FINANCIAL_HARDSHIP


def test_escalate_to_human_args_rejects_invalid_reason() -> None:
    with pytest.raises(ValidationError):
        EscalateToHumanArgs.model_validate({"reason": "NOT_A_REASON", "rationale": "x"})


def test_escalate_to_human_args_rejects_missing_rationale() -> None:
    with pytest.raises(ValidationError):
        EscalateToHumanArgs.model_validate({"reason": "REQUEST_HUMAN"})


@pytest.mark.parametrize("forbidden_key", ["queue", "reviewer_role", "reviewer", "destination"])
def test_escalate_to_human_args_rejects_any_destination_shaped_extra_field(
    forbidden_key: str,
) -> None:
    """AC4: escalate_to_human's args model has no queue/role/reviewer field
    at all -- a raw args dict that includes one is rejected as invalid, not
    silently dropped. Only `rules_engine.routing.route_escalation` decides
    the destination."""
    raw_args = {
        "reason": "REQUEST_HUMAN",
        "rationale": "Customer asked to speak to a person.",
        forbidden_key: "COLLECTIONS_REVIEW",
    }
    with pytest.raises(ValidationError):
        EscalateToHumanArgs.model_validate(raw_args)


def test_escalate_to_human_args_model_has_no_destination_field_declared() -> None:
    """Belt-and-braces on AC4: not just rejected at validation time, but the
    field genuinely does not exist on the model."""
    field_names = set(EscalateToHumanArgs.model_fields)
    assert field_names == {"reason", "rationale"}


def test_eligible_options_result_arrangement_options_defaults_to_empty_list() -> None:
    """AC5: arrangement_options is always empty in Slice 1."""
    result = EligibleOptionsResult(
        account_id=_ACCOUNT_ID,
        payable_options=[],
        ptp_date_window=PtpDateWindowResult(earliest=date(2026, 10, 1), latest=date(2026, 10, 31)),
    )
    assert result.arrangement_options == []
