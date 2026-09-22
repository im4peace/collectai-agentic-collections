"""E5-S3 AC4: prompt construction includes only allow-listed fields. A
forbidden field (e.g. `national_id`) added to the raw context is structurally
excluded, never merely filtered by convention."""

from __future__ import annotations

from collectai.ai_orchestration.prompts.builder import (
    ALLOWED_PROMPT_FIELDS,
    AllowedPromptContext,
    build_prompt_context,
    render_prompt,
)

_FORBIDDEN_VALUE = "NID-DEMO-0001"


def _raw_context_with_forbidden_field() -> dict[str, object]:
    return {
        "customer_display_name": "Jordan Rivera",
        "account_reference": "acc_000123",
        "delinquency_summary": "60 days past due, $1,240.00 outstanding",
        "priority_band": "HIGH",
        "eligible_options_summary": "3-month payment plan available",
        "national_id": _FORBIDDEN_VALUE,
        "raw_account_number": "4111111111111111",
    }


def test_forbidden_field_is_absent_from_the_built_context() -> None:
    context = build_prompt_context(_raw_context_with_forbidden_field())

    assert not hasattr(context, "national_id")
    assert not hasattr(context, "raw_account_number")
    assert "national_id" not in AllowedPromptContext.model_fields
    assert context.customer_display_name == "Jordan Rivera"


def test_forbidden_field_value_never_appears_in_the_rendered_prompt() -> None:
    context = build_prompt_context(_raw_context_with_forbidden_field())

    rendered = render_prompt(context)

    assert _FORBIDDEN_VALUE not in rendered
    assert "4111111111111111" not in rendered


def test_allowed_fields_render_correctly_on_the_happy_path() -> None:
    raw = {
        "customer_display_name": "Jordan Rivera",
        "account_reference": "acc_000123",
        "delinquency_summary": "60 days past due, $1,240.00 outstanding",
        "priority_band": "HIGH",
        "eligible_options_summary": "3-month payment plan available",
    }

    context = build_prompt_context(raw)
    rendered = render_prompt(context)

    assert "Jordan Rivera" in rendered
    assert "acc_000123" in rendered
    assert "HIGH" in rendered


def test_allowed_prompt_fields_constant_matches_the_model_fields() -> None:
    assert ALLOWED_PROMPT_FIELDS == frozenset(AllowedPromptContext.model_fields)
