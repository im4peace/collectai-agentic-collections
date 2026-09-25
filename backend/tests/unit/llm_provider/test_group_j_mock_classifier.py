"""Unit tests for `llm_provider._mock_classifier` (Group J: E11-S1, E11-S2).

Exercises the classifier directly against `ProviderRequest`s shaped like the
real ones `_chat_classification.py`/`_chat_proposal_flow.py` build (system
prompt's opening sentence, single `{"role": "user", "content": ...}`
message), independent of the prompt-builder modules themselves -- this is a
pure unit test of the pattern-matching, not an integration test of prompt
construction.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.ai_orchestration.schemas.proposal_extraction import ProposalExtractionResult
from collectai.ai_orchestration.structured_output import validate_structured_output
from collectai.llm_provider._mock_classifier import classify
from collectai.llm_provider.base import ProviderRequest

_INTENT_SYSTEM = "You are CollectAI's chat intent classifier. You disclose, if asked, ..."
_PROPOSAL_SYSTEM = "You are CollectAI's chat proposal-extraction assistant. You never ..."


def _request(system: str, message: str) -> ProviderRequest:
    return ProviderRequest(
        system=system, messages=[{"role": "user", "content": message}], max_tokens=200
    )


# Intent classification ------------------------------------------------


def test_promise_to_pay_phrasing_classifies_as_promise_to_pay() -> None:
    result = classify(_request(_INTENT_SYSTEM, "I promise to pay 100 in 5 days."))
    parsed = validate_structured_output(result.content, IntentResult)
    assert parsed.label == "PROMISE_TO_PAY"


def test_payment_plan_phrasing_classifies_as_payment_plan() -> None:
    result = classify(_request(_INTENT_SYSTEM, "Can I set up a payment plan?"))
    parsed = validate_structured_output(result.content, IntentResult)
    assert parsed.label == "PAYMENT_PLAN"


def test_installment_followup_still_classifies_as_payment_plan() -> None:
    """The second turn of a payment-plan conversation (E8-S1's
    `arrangement_choice_message` reply, echoed back by the customer) is
    re-classified from scratch, same as any other message -- it must still
    say something that resolves to PAYMENT_PLAN, not drop back to UNKNOWN."""
    result = classify(_request(_INTENT_SYSTEM, "I'll take the payment plan with 3 installments."))
    parsed = validate_structured_output(result.content, IntentResult)
    assert parsed.label == "PAYMENT_PLAN"


@pytest.mark.parametrize(
    ("message", "expected_label"),
    [
        ("I want to pay now please.", "PAY_NOW"),
        ("This charge is a dispute, it's not my debt.", "DISPUTE"),
        ("I lost my job and I'm facing financial hardship.", "FINANCIAL_HARDSHIP"),
        ("I'd like to speak to a human please.", "REQUEST_HUMAN"),
        ("What is my current balance?", "UNKNOWN"),
    ],
)
def test_other_recognized_phrasings(message: str, expected_label: str) -> None:
    result = classify(_request(_INTENT_SYSTEM, message))
    parsed = validate_structured_output(result.content, IntentResult)
    assert parsed.label == expected_label


def test_unrecognized_system_prompt_falls_back_to_the_old_fixed_response() -> None:
    """A prompt this module does not recognize (e.g. NBA generation) is
    untouched -- still the same non-JSON `"Acknowledged."` as before this
    module existed."""
    result = classify(_request("You are CollectAI's next-best-action generator.", "anything"))
    assert result.content == "Acknowledged."


# Proposal extraction ----------------------------------------------------


def test_promise_to_pay_extraction_reads_amount_and_days() -> None:
    result = classify(_request(_PROPOSAL_SYSTEM, "I promise to pay 123.45 in 5 days."))
    parsed = validate_structured_output(result.content, ProposalExtractionResult)
    assert parsed.promised_amount == "123.45"
    assert parsed.promised_date == date.today() + timedelta(days=5)
    assert parsed.installment_count is None


def test_payment_plan_extraction_reads_installment_count() -> None:
    result = classify(_request(_PROPOSAL_SYSTEM, "I'll take the 3 installments option."))
    parsed = validate_structured_output(result.content, ProposalExtractionResult)
    assert parsed.installment_count == 3
    assert parsed.promised_amount is None


def test_extraction_with_no_recognizable_values_returns_an_all_none_result() -> None:
    result = classify(_request(_PROPOSAL_SYSTEM, "I'm not sure yet."))
    parsed = validate_structured_output(result.content, ProposalExtractionResult)
    assert parsed.promised_amount is None
    assert parsed.promised_date is None
    assert parsed.installment_count is None


# MockProvider() (responses=None) is never affected for explicit scripts --
# covered by test_e5_s1_mock.py's own existing suite (still passing
# unchanged, verified separately).
