"""Deterministic reply planning for one classified chat message (E6-S1
AC4, AC5). Split out of `chat_flow.py` to keep that module under the
code-gen skill's 300-line block threshold: this module owns only the pure
`plan_reply` dispatch (and its per-branch helpers); `_chat_turn_processing`
applies the `_ReplyPlan` it returns (persistence, escalation reporting).

CLAUDE.md's core engineering principle: nothing here calls an LLM or does
I/O. `plan_reply` takes the already-classified `IntentResult` and the
already-computed `SafetyDecision` (`ai_orchestration.safety_precedence`) and
returns data describing what to say and what bookkeeping to apply -- the
one deterministic function that turns D-016's precedence into an actual
customer-facing outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectai.ai_orchestration.safety_precedence import SafetyDecision
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.api.schemas.me import customer_message_for
from collectai.application._chat_templates import (
    CLARIFICATION_QUESTION,
    transactional_acknowledgement,
)
from collectai.types.enums import ConversationStatus, EscalationReason, Intent, MessageLabel
from collectai.types.enums import SpecialRequest as _SpecialRequest


@dataclass(frozen=True, slots=True)
class ReplyPlan:
    """What to say, and what bookkeeping to apply, for one classified
    message."""

    content: str
    labels: tuple[MessageLabel, ...]
    clarification_count: int
    conversation_status: ConversationStatus
    escalation_reason: EscalationReason | None


def plan_reply(
    intent_result: IntentResult,
    decision: SafetyDecision,
    clarification_count: int,
    max_clarification_turns: int,
) -> ReplyPlan:
    """Pure dispatch: exactly one of AC4's sensitive-pause, AC5's two
    escalation-reporting paths, AC5's clarification path, or AC4's
    transactional-acknowledgement path applies to any one `IntentResult`.
    `Intent`'s seven members are each reachable from exactly one branch
    below (REQUEST_HUMAN first since it is always sensitive but AC5 gives it
    its own immediate-escalation handling distinct from other sensitive
    intents; UNKNOWN's clarification counting only applies when it is *not*
    also flagged sensitive by `vulnerability_detected`/`special_request`)."""
    if intent_result.label is Intent.REQUEST_HUMAN:
        return _plan_request_human()
    if decision.sensitive:
        return _plan_sensitive(intent_result)
    if intent_result.label is Intent.UNKNOWN:
        return _plan_unknown(clarification_count, max_clarification_turns)
    if decision.proposal_execution_permitted:
        return _plan_transactional(intent_result.label)
    raise AssertionError(  # pragma: no cover - defensive: the branches above are exhaustive
        f"Unreachable IntentResult/SafetyDecision combination: {intent_result!r}, {decision!r}"
    )


def _plan_request_human() -> ReplyPlan:
    return ReplyPlan(
        content=customer_message_for(EscalationReason.REQUEST_HUMAN),
        labels=(MessageLabel.HUMAN_HANDOFF,),
        clarification_count=0,
        conversation_status=ConversationStatus.HANDED_OFF,
        escalation_reason=EscalationReason.REQUEST_HUMAN,
    )


def _plan_sensitive(intent_result: IntentResult) -> ReplyPlan:
    reason = _sensitive_customer_message_reason(intent_result)
    return ReplyPlan(
        content=customer_message_for(reason),
        labels=(),
        clarification_count=0,
        conversation_status=ConversationStatus.ACTIVE,
        escalation_reason=None,
    )


def _sensitive_customer_message_reason(intent_result: IntentResult) -> EscalationReason:
    """AC4's own precedence, restated for template selection only (no
    escalation report is written for any of these -- see
    `_chat_escalation_reporting.py`'s module docstring)."""
    if intent_result.vulnerability_detected:
        return EscalationReason.VULNERABLE_CUSTOMER
    if intent_result.label is Intent.DISPUTE:
        return EscalationReason.DISPUTE
    if intent_result.label is Intent.FINANCIAL_HARDSHIP:
        return EscalationReason.FINANCIAL_HARDSHIP
    if intent_result.special_request is _SpecialRequest.SETTLEMENT:
        return EscalationReason.SETTLEMENT_REQUEST
    return EscalationReason.POLICY_EXCEPTION


def _plan_unknown(clarification_count: int, max_clarification_turns: int) -> ReplyPlan:
    new_count = clarification_count + 1
    if new_count <= max_clarification_turns:
        return ReplyPlan(
            content=CLARIFICATION_QUESTION,
            labels=(),
            clarification_count=new_count,
            conversation_status=ConversationStatus.ACTIVE,
            escalation_reason=None,
        )
    return ReplyPlan(
        content=customer_message_for(EscalationReason.UNRESOLVED_UNKNOWN),
        labels=(MessageLabel.HUMAN_HANDOFF,),
        clarification_count=0,
        conversation_status=ConversationStatus.ACTIVE,
        escalation_reason=EscalationReason.UNRESOLVED_UNKNOWN,
    )


def _plan_transactional(label: Intent) -> ReplyPlan:
    return ReplyPlan(
        content=transactional_acknowledgement(label),
        labels=(),
        clarification_count=0,
        conversation_status=ConversationStatus.ACTIVE,
        escalation_reason=None,
    )
