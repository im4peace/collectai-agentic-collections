"""Keyword-based structured-output classifier backing `MockProvider`'s
default (unscripted) response path (Group J: E11-S1, E11-S2).

`llm_provider.factory.get_provider` wires a bare `MockProvider()` -- no
explicit `responses` -- for every real running `LLM_MODE=MOCK` server (the
default everywhere: `.env.example`, `docker-compose.yml`, CI). Before this
module existed, that path always returned the same fixed, non-JSON
`"Acknowledged."` string regardless of what the customer typed, which fails
schema validation on every turn (`structured_output.validate_structured_
output`) and makes the chat surface fall through to `AI_UNAVAILABLE` no
matter what -- a live demo/e2e run could never see a real PROMISE_TO_PAY or
PAYMENT_PLAN proposal. This module recognizes enough common phrasing for
those two intents (plus a few related ones, for safety/consistency) to
produce real, schema-valid output instead.

Every `MockProvider(responses=[...])` construction -- every existing unit
and API test that scripts its own `ProviderResult` sequence -- is completely
unaffected: this module is reached only from `MockProvider`'s
`responses is None` branch, never when explicit scripts are given.

Deliberately narrow and never guesses past what it can confidently
pattern-match: anything this module does not recognize falls back to the
same fixed `"Acknowledged."` response as before, which still safely fails
schema validation and routes to the existing `AI_UNAVAILABLE` path -- this
module adds a capability, it never removes the previous safe-fallback
behaviour for unrecognized input. `MockProvider` remains a MOCK by every
other meaning of that label in this codebase (CLAUDE.md, `api-contracts.md`
`DataLabel.MOCK`): this is pattern-matching against synthetic demo text,
never a real model call, and is never evidence of real-model quality.

Group K (E11-S3, E11-S4) adds three more narrow, deterministic recognitions
on the same path: a bereavement wording sets the advisory
`vulnerability_detected` signal, a job-loss wording yields the `JOB_LOSS`
hardship indicator, and a few dispute wordings yield a dispute category.
Production behaviour, `LIVE` mode and every explicitly scripted
`MockProvider(responses=[...])` are untouched; the normal orchestration,
schema validation, rules, escalation and audit run exactly as before on the
output.

Date extraction uses the real wall clock (`date.today()`), not the
application's injectable `Clock` -- this module has no access to it (a
provider only ever receives a `ProviderRequest`). This is safe for the
journeys that need it (E11-S1, E11-S2) because they always create a
PROMISE_TO_PAY/PAYMENT_PLAN proposal before advancing the demo clock, when
a freshly-installed `SimulatedClock` is still seeded to the real current
instant (`api/app.py`'s own `create_app` docstring).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from collectai.llm_provider.base import ProviderRequest, ProviderResult

_MODEL_ID = "mock-model-1"
_INTENT_SYSTEM_PREFIX = "You are CollectAI's chat intent classifier."
_PROPOSAL_SYSTEM_PREFIX = "You are CollectAI's chat proposal-extraction assistant."
_HARDSHIP_SYSTEM_PREFIX = "You are CollectAI's chat hardship-classification assistant."
_DISPUTE_SYSTEM_PREFIX = "You are CollectAI's chat dispute-classification assistant."

_ACKNOWLEDGED = ProviderResult(
    content="Acknowledged.", model_id=_MODEL_ID, latency_ms=0.0, input_tokens=0, output_tokens=0
)

# Order matters in `_intent_label`: PAYMENT_PLAN is checked before
# PROMISE_TO_PAY so "I promise to pay through a payment plan" -- which
# matches both -- classifies as the more specific PAYMENT_PLAN.
_PAYMENT_PLAN_PATTERN = re.compile(r"payment\s+plan|installment", re.IGNORECASE)
_PROMISE_TO_PAY_PATTERN = re.compile(
    r"promise(?:d|s)?\s+to\s+pay|i\s+(?:can|will)\s+pay", re.IGNORECASE
)
_PAY_NOW_PATTERN = re.compile(r"\bpay\s+(?:it\s+)?now\b|\bpay\s+today\b", re.IGNORECASE)
_DISPUTE_PATTERN = re.compile(
    r"\bdispute\b|not\s+my\s+(?:debt|charge)|didn'?t\s+(?:make|buy)\s+this", re.IGNORECASE
)
_HARDSHIP_PATTERN = re.compile(
    r"hardship|lost\s+my\s+job|can'?t\s+afford|financial\s+difficult", re.IGNORECASE
)
_HUMAN_PATTERN = re.compile(r"\bhuman\b|\bspeak\s+to\s+(?:someone|an?\s+agent)\b", re.IGNORECASE)

# Group K (E11-S3, E11-S4): the narrow, deterministic phrasing the two
# journeys need beyond intent labels -- a bereavement wording for the
# vulnerability signal, a job-loss wording for the hardship indicator, and
# three dispute-category wordings. Deliberately not a general classifier:
# anything else yields the schema's own safe default (no vulnerability, an
# empty indicator list, dispute category OTHER), which the domain services
# already handle.
_BEREAVEMENT_PATTERN = re.compile(r"passed\s+away|bereave(?:d|ment)|\bfuneral\b", re.IGNORECASE)
_JOB_LOSS_PATTERN = re.compile(
    r"lost\s+my\s+job|laid\s+off|made\s+redundant|lost\s+my\s+employment", re.IGNORECASE
)
_NOT_MY_DEBT_PATTERN = re.compile(
    r"not\s+my\s+(?:debt|charge)|didn'?t\s+(?:make|buy)\s+this", re.IGNORECASE
)
_ALREADY_PAID_PATTERN = re.compile(r"already\s+paid", re.IGNORECASE)
_AMOUNT_INCORRECT_PATTERN = re.compile(
    r"(?:wrong|incorrect)\s+amount|amount\s+is\s+(?:wrong|incorrect)", re.IGNORECASE
)

_AMOUNT_PATTERN = re.compile(r"pay\s+(?:aed\s*)?(\d+(?:\.\d{1,2})?)", re.IGNORECASE)
_DAYS_PATTERN = re.compile(r"in\s+(\d+)\s+days?", re.IGNORECASE)
_INSTALLMENTS_PATTERN = re.compile(r"(\d+)\s*[- ]?installments?", re.IGNORECASE)


def classify(request: ProviderRequest) -> ProviderResult:
    """The `MockProvider(responses=None)` default: dispatches on `request
    .system`'s literal opening sentence (`_chat_classification.py`'s and
    `_chat_proposal_flow.py`'s own prompt-builder modules each start their
    system prompt with a fixed, distinguishing sentence -- the only
    discriminator a stateless provider call has, since `ProviderRequest`
    carries no explicit schema identifier)."""
    system = request.system or ""
    message = _latest_user_message(request)
    if system.startswith(_INTENT_SYSTEM_PREFIX):
        return _classify_intent(message)
    if system.startswith(_PROPOSAL_SYSTEM_PREFIX):
        return _extract_proposal(message)
    if system.startswith(_HARDSHIP_SYSTEM_PREFIX):
        return _extract_hardship(message)
    if system.startswith(_DISPUTE_SYSTEM_PREFIX):
        return _extract_dispute(message)
    return _ACKNOWLEDGED


def _latest_user_message(request: ProviderRequest) -> str:
    for entry in reversed(request.messages):
        if entry.get("role") == "user":
            return entry.get("content", "")
    return ""


def _intent_label(message: str) -> tuple[str, str]:
    if _PAYMENT_PLAN_PATTERN.search(message):
        return "PAYMENT_PLAN", "Message referenced a payment plan or installments."
    if _PROMISE_TO_PAY_PATTERN.search(message):
        return "PROMISE_TO_PAY", "Message committed to a future payment."
    if _PAY_NOW_PATTERN.search(message):
        return "PAY_NOW", "Message asked to pay immediately."
    if _DISPUTE_PATTERN.search(message):
        return "DISPUTE", "Message disputed a charge or debt."
    if _HARDSHIP_PATTERN.search(message):
        return "FINANCIAL_HARDSHIP", "Message described a financial hardship."
    if _HUMAN_PATTERN.search(message):
        return "REQUEST_HUMAN", "Message asked to speak with a human."
    return "UNKNOWN", "Message did not match a known intent pattern."


def _classify_intent(message: str) -> ProviderResult:
    label, rationale = _intent_label(message)
    vulnerable = _BEREAVEMENT_PATTERN.search(message) is not None
    content: dict[str, object] = {
        "label": label,
        "confidence": 0.95,
        "rationale": rationale,
        "vulnerability_detected": vulnerable,
        "special_request": "NONE",
    }
    if vulnerable:
        content["vulnerability_category"] = "BEREAVEMENT"
        content["vulnerability_rationale"] = "Message mentioned a recent bereavement."
    return ProviderResult(
        content=content, model_id=_MODEL_ID, latency_ms=0.0, input_tokens=0, output_tokens=0
    )


def _extract_proposal(message: str) -> ProviderResult:
    content: dict[str, object] = {}
    amount_match = _AMOUNT_PATTERN.search(message)
    if amount_match:
        content["promised_amount"] = amount_match.group(1)
    days_match = _DAYS_PATTERN.search(message)
    if days_match:
        content["promised_date"] = date.today() + timedelta(days=int(days_match.group(1)))
    installments_match = _INSTALLMENTS_PATTERN.search(message)
    if installments_match:
        content["installment_count"] = int(installments_match.group(1))
    return ProviderResult(
        content=content, model_id=_MODEL_ID, latency_ms=0.0, input_tokens=0, output_tokens=0
    )


def _extract_hardship(message: str) -> ProviderResult:
    indicators = ["JOB_LOSS"] if _JOB_LOSS_PATTERN.search(message) else []
    return ProviderResult(
        content={"indicator_types": indicators},
        model_id=_MODEL_ID,
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
    )


def _dispute_category(message: str) -> str:
    if _NOT_MY_DEBT_PATTERN.search(message):
        return "NOT_MY_DEBT"
    if _ALREADY_PAID_PATTERN.search(message):
        return "ALREADY_PAID"
    if _AMOUNT_INCORRECT_PATTERN.search(message):
        return "AMOUNT_INCORRECT"
    return "OTHER"


def _extract_dispute(message: str) -> ProviderResult:
    return ProviderResult(
        content={"category": _dispute_category(message)},
        model_id=_MODEL_ID,
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
    )


__all__ = ["classify"]
