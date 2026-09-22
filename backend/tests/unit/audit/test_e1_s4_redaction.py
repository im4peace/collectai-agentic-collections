"""E1-S4 AC4: secrets and prohibited identifiers are redacted before an
audit event is stored."""

from __future__ import annotations

from collectai.audit.redaction import redact_text, redact_value


def test_anthropic_shaped_api_key_is_redacted() -> None:
    text = "provider call used key sk-ant-api03-abcdEFGH12345678ijklMNOP for this request"

    redacted = redact_text(text)

    assert "[REDACTED]" in redacted
    assert "sk-ant-api03-abcdEFGH12345678ijklMNOP" not in redacted


def test_generic_bearer_token_is_redacted() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo"

    redacted = redact_text(text)

    assert "[REDACTED]" in redacted
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo" not in redacted


def test_card_like_digit_run_is_redacted() -> None:
    text = "customer mentioned a card ending pattern 4111111111111111 in chat"

    redacted = redact_text(text)

    assert "[REDACTED]" in redacted
    assert "4111111111111111" not in redacted


def test_ssn_shaped_value_is_redacted() -> None:
    text = "reference number 078-05-1120 was mentioned"

    redacted = redact_text(text)

    assert "[REDACTED]" in redacted
    assert "078-05-1120" not in redacted


def test_cvv_labelled_value_is_redacted() -> None:
    text = "customer read out CVV: 482 during the call"

    redacted = redact_text(text)

    assert "[REDACTED]" in redacted
    assert "482" not in redacted


def test_text_with_no_secret_pattern_is_unchanged() -> None:
    text = "Account acc_000123 has an outstanding balance of $1,240.00 due 2026-11-01."

    redacted = redact_text(text)

    assert redacted == text


def test_redact_value_recurses_through_nested_dicts_and_lists() -> None:
    value = {
        "summary": "call notes",
        "raw_output": {
            "tool_calls": [
                {"argument": "key is sk-ant-api03-abcdEFGH12345678"},
                {"argument": "no secret here"},
            ]
        },
    }

    redacted = redact_value(value)

    assert isinstance(redacted, dict)
    tool_calls = redacted["raw_output"]["tool_calls"]  # type: ignore[index]
    assert "[REDACTED]" in tool_calls[0]["argument"]
    assert tool_calls[1]["argument"] == "no secret here"


def test_redact_value_passes_non_string_scalars_through_unchanged() -> None:
    assert redact_value(42) == 42
    assert redact_value(None) is None
    assert redact_value(True) is True
