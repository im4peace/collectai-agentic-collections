"""Schema validation for LLM output (E5-S2 AC1, AC4; code-gen skill's LLM
Integration section: "Always Use Structured Output", "Validate Before
Using", "No Silent Fallbacks").

Pure validation only: takes the raw content an `LlmProvider` already
returned and validates it against a caller-supplied Pydantic schema.
Deliberately owns no retry loop and no provider call -- `orchestrator.py`
is the only caller and is responsible for the bounded retry (AC1), since
only it holds the provider and can issue a correction-prompt follow-up call.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredOutputError(Exception):
    """`content` did not validate against `schema`. Carries the raw content
    so the caller can store it for audit (AC1: "invalid output stored in
    the audit event") -- never silently discarded, never replaced by a
    defaulted instance."""

    def __init__(self, *, raw_content: str, validation_error: str) -> None:
        self.raw_content = raw_content
        self.validation_error = validation_error
        super().__init__(f"LLM output failed schema validation: {validation_error}")


def validate_structured_output(
    content: str | dict[str, object], schema: type[SchemaT]
) -> SchemaT:
    """Validate `content` (a provider's raw `ProviderResult.content`)
    against `schema`. Raises `StructuredOutputError` on any shape, type or
    value failure -- never returns a partially-populated or defaulted
    instance."""
    raw_for_error = content if isinstance(content, str) else str(content)
    try:
        if isinstance(content, str):
            return schema.model_validate_json(content)
        return schema.model_validate(content)
    except ValidationError as exc:
        raise StructuredOutputError(raw_content=raw_for_error, validation_error=str(exc)) from exc
