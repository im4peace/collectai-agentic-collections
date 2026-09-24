"""E6-S1 AC2, AC3: `IntentResult` schema validation.

Label restricted to `Intent`'s seven members (AC2) -- an eighth,
unrecognized label such as `VULNERABLE_CUSTOMER` must be rejected, not
silently coerced. `vulnerability_detected` is required (AC3): an output
that omits it must fail schema validation, proving Pydantic's own required
-field behavior does what AC3 asks for rather than assuming it.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.ai_orchestration.structured_output import (
    StructuredOutputError,
    validate_structured_output,
)
from collectai.types.enums import Intent, SpecialRequest, VulnerabilityCategory


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "label": "PROMISE_TO_PAY",
        "confidence": 0.82,
        "rationale": "Customer explicitly offered to pay next week.",
        "vulnerability_detected": False,
        "vulnerability_category": None,
        "vulnerability_rationale": "",
        "special_request": "NONE",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("label", list(Intent))
def test_every_one_of_the_seven_allowed_labels_validates(label: Intent) -> None:
    payload = _valid_payload(label=label.value)
    result = IntentResult.model_validate(payload)
    assert result.label is label


def test_unknown_label_vulnerable_customer_is_rejected() -> None:
    """AC2: 'an unknown label, including VULNERABLE_CUSTOMER, is rejected'."""
    payload = _valid_payload(label="VULNERABLE_CUSTOMER")
    with pytest.raises(ValidationError):
        IntentResult.model_validate(payload)


def test_unknown_label_through_the_orchestrator_structured_output_path_is_rejected() -> None:
    """Same rejection, exercised through the exact path
    `ai_orchestration.orchestrator.run_ai_interaction` uses on a raw
    provider string (hostile-provider style, mirroring
    `test_e5_s2_hostile_provider.py`)."""
    raw = json.dumps(_valid_payload(label="VULNERABLE_CUSTOMER"))
    with pytest.raises(StructuredOutputError):
        validate_structured_output(raw, IntentResult)


def test_missing_vulnerability_detected_fails_schema_validation() -> None:
    """AC3: 'an output missing vulnerability_detected fails schema
    validation'."""
    payload = _valid_payload()
    del payload["vulnerability_detected"]
    with pytest.raises(ValidationError):
        IntentResult.model_validate(payload)


def test_confidence_above_one_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentResult.model_validate(_valid_payload(confidence=1.5))


def test_confidence_below_zero_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentResult.model_validate(_valid_payload(confidence=-0.1))


def test_unknown_field_is_rejected() -> None:
    payload = _valid_payload()
    payload["action"] = "APPROVE_PAYMENT"
    with pytest.raises(ValidationError):
        IntentResult.model_validate(payload)


def test_vulnerability_category_and_rationale_round_trip_when_detected() -> None:
    payload = _valid_payload(
        label="FINANCIAL_HARDSHIP",
        vulnerability_detected=True,
        vulnerability_category="SERIOUS_ILLNESS_OR_DISABILITY",
        vulnerability_rationale="Customer mentioned a recent hospitalization.",
    )
    result = IntentResult.model_validate(payload)
    assert result.vulnerability_detected is True
    assert result.vulnerability_category is VulnerabilityCategory.SERIOUS_ILLNESS_OR_DISABILITY
    assert result.vulnerability_rationale == "Customer mentioned a recent hospitalization."


def test_vulnerability_rationale_defaults_to_empty_string_not_none() -> None:
    """Design choice documented in `intent.py`: `vulnerability_rationale`
    defaults to `""`, never `None`."""
    payload = _valid_payload()
    del payload["vulnerability_rationale"]
    result = IntentResult.model_validate(payload)
    assert result.vulnerability_rationale == ""


def test_special_request_settlement_round_trips() -> None:
    result = IntentResult.model_validate(_valid_payload(special_request="SETTLEMENT"))
    assert result.special_request is SpecialRequest.SETTLEMENT


def test_unknown_special_request_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentResult.model_validate(_valid_payload(special_request="DISCOUNT"))
