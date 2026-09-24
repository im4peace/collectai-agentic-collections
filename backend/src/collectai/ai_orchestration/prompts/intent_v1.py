"""Intent classification prompt, version `intent_v1` (E6-S1 AC2, AC3).

Builds the `ProviderRequest` `application.chat_flow` hands to
`ai_orchestration.orchestrator.run_ai_interaction` for one customer chat
message. The system prompt is explicit that the model only classifies and
never decides a financial action or a human-escalation outcome (CLAUDE.md's
core engineering principle) -- `ai_orchestration.safety_precedence` is the
deterministic function that actually applies D-016's safety precedence to
whatever this prompt's response contains.
"""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.llm_provider.base import ProviderRequest

PROMPT_VERSION = "intent_v1"

_DEFAULT_MAX_TOKENS = 500

_SYSTEM_PROMPT_TEMPLATE = """You are CollectAI's chat intent classifier. You disclose, if asked, \
that you are an AI assistant, not a human collections officer.

Classify the customer's message into exactly one of these seven intents: \
PAY_NOW, PROMISE_TO_PAY, PAYMENT_PLAN, FINANCIAL_HARDSHIP, DISPUTE, \
REQUEST_HUMAN, UNKNOWN.

You never decide, approve or execute a payment, promise-to-pay, payment \
plan, settlement or policy exception -- you only classify the message and \
report advisory safety signals. A deterministic system, not you, decides \
what happens next.

Also report, as advisory signals only:
- vulnerability_detected: true if the message suggests the customer may be \
in a vulnerable situation (bereavement, serious illness or disability, \
mental health concern, domestic abuse or coercion, limited capacity to \
understand, or a language/communication barrier), else false.
- vulnerability_category: the closest matching category if \
vulnerability_detected is true, else omit it.
- vulnerability_rationale: a short, respectful explanation if \
vulnerability_detected is true, else an empty string.
- special_request: SETTLEMENT if the customer asks to settle for less than \
owed, POLICY_EXCEPTION if they ask for terms outside normal policy, else \
NONE.

Respond with a single JSON object matching this schema exactly, with no \
extra fields:
{schema}

Context:
{context}"""


def build_intent_request(
    *, context: AllowedPromptContext, message: str, max_tokens: int = _DEFAULT_MAX_TOKENS
) -> ProviderRequest:
    """Build the classification request for `message`. `context` is already
    restricted to `AllowedPromptContext`'s allow-list (E5-S3 AC4) by the
    caller -- this module never reads a raw context mapping itself."""
    system = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=IntentResult.model_json_schema(), context=render_prompt(context)
    )
    return ProviderRequest(
        system=system,
        messages=[{"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
