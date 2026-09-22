"""Tests for the `LlmProvider` contract shapes (E5-S1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from collectai.llm_provider.base import ProviderRequest, ProviderResult, ProviderTimeout


def test_provider_request_accepts_a_minimal_valid_shape() -> None:
    request = ProviderRequest(
        system="You are a collections assistant.",
        messages=[{"role": "user", "content": "What is my balance?"}],
        max_tokens=256,
    )

    assert request.system == "You are a collections assistant."
    assert request.max_tokens == 256


def test_provider_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError, match="messages"):
        ProviderRequest(messages=[], max_tokens=256)


def test_provider_request_rejects_non_positive_max_tokens() -> None:
    with pytest.raises(ValidationError, match="max_tokens"):
        ProviderRequest(messages=[{"role": "user", "content": "hi"}], max_tokens=0)


def test_provider_result_carries_model_id_latency_and_token_usage() -> None:
    result = ProviderResult(
        content="Your next payment is due on 2026-10-05.",
        model_id="mock-model-1",
        latency_ms=42.5,
        input_tokens=120,
        output_tokens=18,
    )

    assert result.model_id == "mock-model-1"
    assert result.latency_ms == 42.5
    assert result.input_tokens == 120
    assert result.output_tokens == 18


def test_provider_result_allows_missing_token_usage() -> None:
    result = ProviderResult(content="ack", model_id="mock-model-1", latency_ms=1.0)

    assert result.input_tokens is None
    assert result.output_tokens is None


def test_provider_result_rejects_model_id_over_120_characters() -> None:
    with pytest.raises(ValidationError, match="model_id"):
        ProviderResult(content="ack", model_id="m" * 121, latency_ms=1.0)


def test_provider_timeout_reports_provider_and_timeout_seconds() -> None:
    error = ProviderTimeout(provider="anthropic", timeout_seconds=20)

    assert error.provider == "anthropic"
    assert error.timeout_seconds == 20
    assert "20" in str(error)
    assert "anthropic" in str(error)
