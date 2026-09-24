"""Proposal-extraction prompt, version `proposal_v1` (E6-S2, E6-S3).

Builds the `ProviderRequest` `application._chat_proposal_flow` hands to
`ai_orchestration.orchestrator.run_ai_interaction` once safety precedence has
already permitted proposal execution for a PROMISE_TO_PAY or PAY_NOW
message. The model only extracts what the customer already said; it never
decides validity (`rules_engine.ptp_rules.validate_ptp` and the
payable-amounts service do that, deterministically, afterward).
"""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
from collectai.ai_orchestration.schemas.proposal_extraction import ProposalExtractionResult
from collectai.llm_provider.base import ProviderRequest

PROMPT_VERSION = "proposal_v1"

_DEFAULT_MAX_TOKENS = 400

_SYSTEM_PROMPT_TEMPLATE = """You are CollectAI's chat proposal-extraction assistant. You never \
decide, approve or execute a payment or promise-to-pay -- you only extract \
what the customer already said, from their message.

If the customer is offering to promise a payment (a "promise to pay"), \
extract promised_amount (as a plain decimal string, e.g. "250.00") and \
promised_date (ISO 8601, e.g. "2026-10-15") if and only if the customer \
stated them. Leave a field null if it was not stated -- never invent or \
estimate a value.

If the customer wants to pay now, extract payment_option as OVERDUE_AMOUNT \
(paying the overdue amount) or FULL_BALANCE (paying the full outstanding \
balance) if and only if the customer's message makes their choice clear \
among the listed eligible options. Leave it null if unclear.

Respond with a single JSON object matching this schema exactly, with no \
extra fields:
{schema}

Context:
{context}"""


def build_proposal_extraction_request(
    *, context: AllowedPromptContext, message: str, max_tokens: int = _DEFAULT_MAX_TOKENS
) -> ProviderRequest:
    """Build the extraction request for `message`. `context` is already
    restricted to `AllowedPromptContext`'s allow-list (E5-S3 AC4) by the
    caller, which is expected to have set `eligible_options_summary` to the
    payable amounts/PTP date window so the model can ground its extraction
    against real, service-returned numbers rather than the customer's own
    unchecked claim."""
    system = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=ProposalExtractionResult.model_json_schema(), context=render_prompt(context)
    )
    return ProviderRequest(
        system=system,
        messages=[{"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
