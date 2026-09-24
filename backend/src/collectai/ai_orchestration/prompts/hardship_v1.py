"""Hardship-indicator extraction prompt, version `hardship_v1` (E8-S2).

Builds the `ProviderRequest` `application._chat_hardship_flow` hands to
`ai_orchestration.orchestrator.run_ai_interaction` once a message has been
classified `Intent.FINANCIAL_HARDSHIP`. The model only classifies which
indicator types the customer's own words best match; it never promises or
implies restructuring or relief (AC2) -- that instruction is enforced
twice: here, and structurally by `HardshipExtractionResult`'s own schema
(no `relief`/`restructuring`/`approved` field exists for the model to fill
in even if it tried).
"""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
from collectai.ai_orchestration.schemas.hardship_extraction import HardshipExtractionResult
from collectai.llm_provider.base import ProviderRequest

PROMPT_VERSION = "hardship_v1"

_DEFAULT_MAX_TOKENS = 200

_SYSTEM_PROMPT_TEMPLATE = """You are CollectAI's chat hardship-classification assistant. You never \
promise, imply or approve any relief, payment reduction or restructuring -- \
you only classify which hardship indicator(s) the customer's own message \
best matches, for a human reviewer to consider. Do not state or imply what \
will happen as a result anywhere in your response.

Classify indicator_types as zero or more of JOB_LOSS (lost employment), \
INCOME_REDUCTION (reduced hours or pay), MEDICAL_OR_FAMILY_EMERGENCY \
(illness, injury or a family emergency), TEMPORARY_FINANCIAL_DIFFICULTY \
(a short-term cash-flow problem), or OTHER if the message clearly \
describes hardship but none of those specifically match. Leave the list \
empty only if the message does not describe hardship at all.

Respond with a single JSON object matching this schema exactly, with no \
extra fields:
{schema}

Context:
{context}"""


def build_hardship_extraction_request(
    *, context: AllowedPromptContext, message: str, max_tokens: int = _DEFAULT_MAX_TOKENS
) -> ProviderRequest:
    system = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=HardshipExtractionResult.model_json_schema(), context=render_prompt(context)
    )
    return ProviderRequest(
        system=system,
        messages=[{"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
