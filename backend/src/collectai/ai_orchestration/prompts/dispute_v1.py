"""Dispute-category extraction prompt, version `dispute_v1` (E8-S3).

Builds the `ProviderRequest` `application._chat_dispute_flow` hands to
`ai_orchestration.orchestrator.run_ai_interaction` once a message has been
classified `Intent.DISPUTE`. The model only classifies which category the
customer's own words best match; it never judges whether the dispute is
valid (AC2) -- that instruction is enforced twice: here, and structurally
by `DisputeExtractionResult`'s own schema (no `valid`/`outcome` field
exists for the model to fill in even if it tried).
"""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
from collectai.ai_orchestration.schemas.dispute_extraction import DisputeExtractionResult
from collectai.llm_provider.base import ProviderRequest

PROMPT_VERSION = "dispute_v1"

_DEFAULT_MAX_TOKENS = 200

_SYSTEM_PROMPT_TEMPLATE = """You are CollectAI's chat dispute-classification assistant. You never \
judge, confirm or deny whether a customer's dispute is valid -- you only \
classify which category their own message best matches, for a human \
reviewer to investigate. Do not state or imply an opinion on the dispute's \
merits anywhere in your response.

Classify category as one of AMOUNT_INCORRECT (the amount owed is wrong), \
NOT_MY_DEBT (this is not their debt), ALREADY_PAID (they say they already \
paid), FRAUD_OR_UNAUTHORIZED (unauthorized/fraudulent charge), \
FEE_OR_INTEREST_DISPUTE (a fee or interest charge is disputed), or OTHER if \
none of those clearly match. Leave it null only if you cannot tell at all.

Respond with a single JSON object matching this schema exactly, with no \
extra fields:
{schema}

Context:
{context}"""


def build_dispute_extraction_request(
    *, context: AllowedPromptContext, message: str, max_tokens: int = _DEFAULT_MAX_TOKENS
) -> ProviderRequest:
    system = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=DisputeExtractionResult.model_json_schema(), context=render_prompt(context)
    )
    return ProviderRequest(
        system=system,
        messages=[{"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
