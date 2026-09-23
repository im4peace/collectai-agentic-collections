"""E5-S2 AC1, AC4: schema validation for LLM output."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from collectai.ai_orchestration.structured_output import (
    StructuredOutputError,
    validate_structured_output,
)


class _DemoProposal(BaseModel):
    action: str
    amount: str


def test_valid_json_string_validates_into_the_schema() -> None:
    raw = '{"action": "PROPOSE_PTP", "amount": "150.00"}'
    result = validate_structured_output(raw, _DemoProposal)

    assert result == _DemoProposal(action="PROPOSE_PTP", amount="150.00")


def test_valid_dict_content_validates_into_the_schema() -> None:
    content = {"action": "PROPOSE_PTP", "amount": "150.00"}
    result = validate_structured_output(content, _DemoProposal)

    assert result == _DemoProposal(action="PROPOSE_PTP", amount="150.00")


def test_malformed_json_string_raises_structured_output_error_with_raw_content() -> None:
    raw = "not json at all {{{"

    with pytest.raises(StructuredOutputError) as exc_info:
        validate_structured_output(raw, _DemoProposal)

    assert exc_info.value.raw_content == raw


def test_json_missing_a_required_field_raises_structured_output_error() -> None:
    with pytest.raises(StructuredOutputError, match="amount"):
        validate_structured_output('{"action": "PROPOSE_PTP"}', _DemoProposal)


def test_wrong_field_type_raises_structured_output_error() -> None:
    with pytest.raises(StructuredOutputError):
        validate_structured_output({"action": "PROPOSE_PTP", "amount": 150.0}, _DemoProposal)
