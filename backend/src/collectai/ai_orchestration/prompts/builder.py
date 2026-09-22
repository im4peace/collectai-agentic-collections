"""Prompt context assembly restricted to an explicit allow-list (E5-S3 AC4).

`AllowedPromptContext` IS the allow-list: a frozen Pydantic model with a
fixed field set. `build_prompt_context` only ever reads keys that appear in
that field set from an arbitrary raw context mapping, so a forbidden field
(e.g. `national_id`, a raw account number) is never read at all -- there is
no code path that could carry it through to `render_prompt`. This is
deliberately narrow: add a field only when an already-implemented story
(E2-S1 priority band, E2-S3 eligible options, ...) actually produces it.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class AllowedPromptContext(BaseModel):
    """Only these fields may ever reach an AI prompt."""

    model_config = ConfigDict(frozen=True)

    customer_display_name: str
    account_reference: str
    delinquency_summary: str | None = None
    priority_band: str | None = None
    eligible_options_summary: str | None = None


ALLOWED_PROMPT_FIELDS: frozenset[str] = frozenset(AllowedPromptContext.model_fields)


def build_prompt_context(raw_context: Mapping[str, object]) -> AllowedPromptContext:
    """Extract only allow-listed fields from `raw_context`. Keys outside
    `ALLOWED_PROMPT_FIELDS` are structurally never read."""
    filtered = {key: raw_context[key] for key in ALLOWED_PROMPT_FIELDS if key in raw_context}
    return AllowedPromptContext.model_validate(filtered)


def render_prompt(context: AllowedPromptContext) -> str:
    """Render the allow-listed context into prompt text."""
    lines = [
        f"Customer: {context.customer_display_name}",
        f"Account: {context.account_reference}",
    ]
    if context.delinquency_summary:
        lines.append(f"Delinquency: {context.delinquency_summary}")
    if context.priority_band:
        lines.append(f"Priority band: {context.priority_band}")
    if context.eligible_options_summary:
        lines.append(f"Eligible options: {context.eligible_options_summary}")
    return "\n".join(lines)
