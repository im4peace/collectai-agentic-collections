"""Deterministic safety precedence (E6-S1 AC4, D-016).

CLAUDE.md's core engineering principle, applied concretely: the LLM only
classifies (`ai_orchestration.schemas.intent.IntentResult`); this module is
the one deterministic, non-LLM function that decides whether a sensitive
signal overrides a transactional one. `application.chat_flow` calls
`apply_safety_precedence` once per classified message and branches on its
result -- it never lets the model's own label alone decide whether a
transactional template (or, in a later story, a real proposal) may proceed.

`SafetyDecision.proposal_execution_permitted` is the explicit gate a later
story (E6-S2/E6-S3, wiring in real PTP/payment proposal creation) must
thread through before calling `ai_orchestration.tools`/
`application.tool_backend`: this story never executes a proposal itself
(AC4's "no PTP or payment proposal is executed" holds trivially here), but
the gate exists now so that future wiring cannot silently bypass D-016 by
skipping this check.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.types.enums import Intent, SpecialRequest

# AC4: FINANCIAL_HARDSHIP, DISPUTE and REQUEST_HUMAN are sensitive on their
# own, independent of `vulnerability_detected` or `special_request`.
_SENSITIVE_INTENTS: frozenset[Intent] = frozenset(
    {Intent.FINANCIAL_HARDSHIP, Intent.DISPUTE, Intent.REQUEST_HUMAN}
)

# The only labels a later story may ever route to proposal creation for --
# and only when `apply_safety_precedence` finds no sensitive signal at all.
_TRANSACTIONAL_INTENTS: frozenset[Intent] = frozenset(
    {Intent.PAY_NOW, Intent.PROMISE_TO_PAY, Intent.PAYMENT_PLAN}
)


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    """The deterministic outcome of applying D-016 to one `IntentResult`."""

    sensitive: bool
    """True when a sensitive signal is present at all (AC4): vulnerability,
    a sensitive intent label, or a non-NONE special request."""

    automated_treatment_paused: bool
    """AC4: when true, `chat_flow` must not proceed to a transactional
    templated confirmation for this topic -- a sensitive-appropriate holding
    response only."""

    proposal_execution_permitted: bool
    """True only for a transactional label with no sensitive signal at all.
    The gate a future PTP/payment-proposal story must check before ever
    calling `ai_orchestration.tools`."""

    reason: str
    """Human-readable tag for logging/audit context, e.g.
    `"vulnerability_detected"`, `"sensitive_intent:DISPUTE"`,
    `"special_request:SETTLEMENT"`, `"transactional_intent:PAY_NOW"`."""


def apply_safety_precedence(intent_result: IntentResult) -> SafetyDecision:
    """Pure and deterministic (no I/O, no randomness): the same
    `IntentResult` always yields the same `SafetyDecision`. Precedence order
    (AC4, D-016) -- the first matching signal wins and is reported as
    `reason`, but any one of these being true alone is already enough to
    make the message sensitive:

    1. `vulnerability_detected`
    2. `label` in `{FINANCIAL_HARDSHIP, DISPUTE, REQUEST_HUMAN}`
    3. `special_request != NONE`
    4. `label` in `{PAY_NOW, PROMISE_TO_PAY, PAYMENT_PLAN}` (transactional,
       only reached when none of the above apply)
    5. anything else (e.g. UNKNOWN) -- not sensitive, but also not
       transactional, so no proposal path applies either.
    """
    if intent_result.vulnerability_detected:
        return _sensitive("vulnerability_detected")
    if intent_result.label in _SENSITIVE_INTENTS:
        return _sensitive(f"sensitive_intent:{intent_result.label.value}")
    if intent_result.special_request is not SpecialRequest.NONE:
        return _sensitive(f"special_request:{intent_result.special_request.value}")
    if intent_result.label in _TRANSACTIONAL_INTENTS:
        return SafetyDecision(
            sensitive=False,
            automated_treatment_paused=False,
            proposal_execution_permitted=True,
            reason=f"transactional_intent:{intent_result.label.value}",
        )
    return SafetyDecision(
        sensitive=False,
        automated_treatment_paused=False,
        proposal_execution_permitted=False,
        reason=f"non_transactional_intent:{intent_result.label.value}",
    )


def _sensitive(reason: str) -> SafetyDecision:
    return SafetyDecision(
        sensitive=True,
        automated_treatment_paused=True,
        proposal_execution_permitted=False,
        reason=reason,
    )
