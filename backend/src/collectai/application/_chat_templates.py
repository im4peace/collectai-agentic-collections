"""Templated assistant reply text for the chat flow (E6-S1).

Every string here is shown to a customer verbatim as `content_source=
TEMPLATE` -- never model-generated prose. That is deliberate, not an
oversight: this story never lets a raw LLM response reach a customer (the
only LLM call in this story, intent classification, produces a structured
`IntentResult` that is *classified*, not displayed), so E5-S3's
post-generation grounding check does not apply to any message this module
returns.
"""

from __future__ import annotations

from collectai.types.enums import Intent

GREETING_TEXT = (
    "Hi, I'm CollectAI's AI assistant. I can help with payments, promises to pay and "
    "payment plans, and you can ask to talk to a human at any time."
)

CLARIFICATION_QUESTION = (
    "I'm not sure I understood that. Could you tell me a bit more about what you'd "
    "like to do -- for example, make a payment, set up a promise to pay, or talk "
    "about a dispute?"
)

HANDED_OFF_HOLDING_MESSAGE = (
    "Your case is already with a specialist, and they'll follow up with you "
    "directly -- there's no need to repeat your request here."
)

SAFE_FALLBACK_MESSAGE = (
    "I'm having trouble processing that right now. You can talk to a human at any time."
)

_TRANSACTIONAL_ACKNOWLEDGEMENTS: dict[Intent, str] = {
    Intent.PAY_NOW: "Thanks -- I understand you'd like to make a payment now.",
    Intent.PROMISE_TO_PAY: "Thanks -- I understand you'd like to set up a promise to pay.",
    Intent.PAYMENT_PLAN: "Thanks -- I understand you'd like to set up a payment plan.",
}


def transactional_acknowledgement(label: Intent) -> str:
    """A templated acknowledgement for a transactional intent with no
    sensitive signal (AC4) -- never an actual proposal (this story never
    creates one; see `application.chat_flow`'s module docstring)."""
    return _TRANSACTIONAL_ACKNOWLEDGEMENTS[label]
