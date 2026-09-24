"""Next-best-action prompt, version `nba_v1` (E4-S3 AC1, AC2).

Built exclusively from `prompts.builder.AllowedPromptContext` (E5-S3 AC4's
allow-list) -- this module never interpolates raw account/customer data of
its own. `application.recommendation_flow` is the only caller: it resolves
the allow-listed context from deterministic service output, this module only
renders it into a `ProviderRequest`.
"""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import AllowedPromptContext, render_prompt
from collectai.llm_provider.base import ProviderRequest
from collectai.types.enums import NbaAction

NBA_PROMPT_VERSION = "nba_v1"

_DEFAULT_MAX_TOKENS = 600
_ALLOWED_ACTIONS = ", ".join(member.value for member in NbaAction)

_SYSTEM_PROMPT = (
    "You are an assistant that proposes a next-best-action recommendation for "
    "a collections officer working a delinquent account. Respond only with "
    'JSON matching this schema: {"action": <string>, "rationale": <string, '
    '1-1500 characters>, "referenced_factor_ids": [<string>, ...]}. Choose '
    f"`action` from exactly these values: {_ALLOWED_ACTIONS}. Only state "
    "currency amounts, dates, option ids and factor ids that literally "
    "appear in the account context below -- never invent a figure or an id "
    "that is not given to you. Only list a factor id in "
    "`referenced_factor_ids` if it appears in the account context below. If "
    "you are unsure, or the situation looks unusual, choose "
    "ESCALATE_TO_HUMAN_REVIEW."
)


def build_nba_request(
    context: AllowedPromptContext, *, max_tokens: int = _DEFAULT_MAX_TOKENS
) -> ProviderRequest:
    """Render `context` into the `ProviderRequest` for one NBA generation call."""
    return ProviderRequest(
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": render_prompt(context)}],
        max_tokens=max_tokens,
    )


__all__ = ["NBA_PROMPT_VERSION", "build_nba_request"]
