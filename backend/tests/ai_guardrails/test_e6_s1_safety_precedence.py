"""E6-S1 AC4, D-016: `apply_safety_precedence` is a pure, deterministic
function -- the sensitive signal must override a transactional one whenever
both are present in a single classified message.
"""

from __future__ import annotations

from collectai.ai_orchestration.safety_precedence import apply_safety_precedence
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.types.enums import Intent, SpecialRequest


def _intent(
    label: Intent,
    *,
    vulnerability_detected: bool = False,
    special_request: SpecialRequest = SpecialRequest.NONE,
) -> IntentResult:
    return IntentResult(
        label=label,
        confidence=0.9,
        rationale="Classified from the customer's message.",
        vulnerability_detected=vulnerability_detected,
        vulnerability_category=None,
        vulnerability_rationale="",
        special_request=special_request,
    )


def test_pure_transactional_intent_permits_proposal_execution() -> None:
    decision = apply_safety_precedence(_intent(Intent.PROMISE_TO_PAY))

    assert decision.sensitive is False
    assert decision.automated_treatment_paused is False
    assert decision.proposal_execution_permitted is True


def test_pay_now_alone_permits_proposal_execution() -> None:
    decision = apply_safety_precedence(_intent(Intent.PAY_NOW))
    assert decision.proposal_execution_permitted is True


def test_payment_plan_alone_permits_proposal_execution() -> None:
    decision = apply_safety_precedence(_intent(Intent.PAYMENT_PLAN))
    assert decision.proposal_execution_permitted is True


def test_dispute_intent_is_sensitive_and_pauses_automated_treatment() -> None:
    decision = apply_safety_precedence(_intent(Intent.DISPUTE))

    assert decision.sensitive is True
    assert decision.automated_treatment_paused is True
    assert decision.proposal_execution_permitted is False


def test_financial_hardship_intent_is_sensitive() -> None:
    decision = apply_safety_precedence(_intent(Intent.FINANCIAL_HARDSHIP))
    assert decision.sensitive is True
    assert decision.proposal_execution_permitted is False


def test_request_human_intent_is_sensitive() -> None:
    decision = apply_safety_precedence(_intent(Intent.REQUEST_HUMAN))
    assert decision.sensitive is True
    assert decision.proposal_execution_permitted is False


def test_transactional_intent_with_vulnerability_detected_is_overridden_by_sensitivity() -> None:
    """AC4's explicit dual-signal case: 'a message contains both a
    transactional and a sensitive intent, or vulnerability_detected is
    true' -- the sensitive signal wins and no proposal path is permitted."""
    decision = apply_safety_precedence(
        _intent(Intent.PROMISE_TO_PAY, vulnerability_detected=True)
    )

    assert decision.sensitive is True
    assert decision.automated_treatment_paused is True
    assert decision.proposal_execution_permitted is False
    assert decision.reason == "vulnerability_detected"


def test_pay_now_with_settlement_special_request_is_overridden_by_sensitivity() -> None:
    decision = apply_safety_precedence(
        _intent(Intent.PAY_NOW, special_request=SpecialRequest.SETTLEMENT)
    )

    assert decision.sensitive is True
    assert decision.proposal_execution_permitted is False


def test_pay_now_with_policy_exception_special_request_is_overridden_by_sensitivity() -> None:
    decision = apply_safety_precedence(
        _intent(Intent.PAYMENT_PLAN, special_request=SpecialRequest.POLICY_EXCEPTION)
    )

    assert decision.sensitive is True
    assert decision.proposal_execution_permitted is False


def test_unknown_intent_is_neither_sensitive_nor_transactional() -> None:
    decision = apply_safety_precedence(_intent(Intent.UNKNOWN))

    assert decision.sensitive is False
    assert decision.proposal_execution_permitted is False


def test_unknown_intent_with_vulnerability_detected_is_sensitive() -> None:
    decision = apply_safety_precedence(_intent(Intent.UNKNOWN, vulnerability_detected=True))

    assert decision.sensitive is True
    assert decision.proposal_execution_permitted is False


def test_decision_is_pure_and_deterministic_across_repeated_calls() -> None:
    intent_result = _intent(Intent.PROMISE_TO_PAY, vulnerability_detected=True)

    first = apply_safety_precedence(intent_result)
    second = apply_safety_precedence(intent_result)

    assert first == second
