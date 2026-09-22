"""E1-S4 AC1: `AuditEventDraft` carries every caller-supplied audit field,
deliberately excluding the three fields the service assigns itself
(`audit_event_id`, `sequence`, `timestamp`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from collectai.audit.events import AuditEventDraft
from collectai.types.enums import ActorKind, AuditStage, Persona, ProviderMode


def _draft(**overrides: object) -> AuditEventDraft:
    base: dict[str, object] = {
        "correlation_id": "c0ffee5678abcd",
        "stage": AuditStage.AI_INTERPRETATION,
        "event_type": "NBA_GENERATED",
        "actor_kind": ActorKind.AI,
        "actor_persona": None,
        "customer_id": "cus_000101",
        "account_id": "acc_000123",
        "capability": "NEXT_BEST_ACTION",
        "provider": "anthropic",
        "provider_mode": ProviderMode.LIVE,
        "model_id": "claude-sonnet-demo",
        "prompt_version": "nba_v1",
        "policy_version": "policy-v1",
        "input_ref": "ctx_ref_abc123",
        "ai_output": {"action": "SEND_REMINDER"},
        "tool_calls": [],
        "rule_results": {"priority_band": "HIGH"},
        "human_override": None,
        "final_action": "SEND_REMINDER",
        "reason_code": None,
        "resource_type": "recommendation",
        "resource_id": "rec_000001",
        "latency": {"provider_latency_ms": 412.5},
        "token_usage": {"input_tokens": 512, "output_tokens": 128},
    }
    base.update(overrides)
    return AuditEventDraft(**base)  # type: ignore[arg-type]


def test_draft_carries_every_ac1_field() -> None:
    draft = _draft()

    assert draft.correlation_id == "c0ffee5678abcd"
    assert draft.stage is AuditStage.AI_INTERPRETATION
    assert draft.actor_kind is ActorKind.AI
    assert draft.provider_mode is ProviderMode.LIVE
    assert draft.model_id == "claude-sonnet-demo"
    assert draft.policy_version == "policy-v1"
    assert draft.token_usage == {"input_tokens": 512, "output_tokens": 128}


def test_draft_has_no_audit_event_id_sequence_or_timestamp_fields() -> None:
    assert "audit_event_id" not in AuditEventDraft.model_fields
    assert "sequence" not in AuditEventDraft.model_fields
    assert "timestamp" not in AuditEventDraft.model_fields


def test_draft_is_frozen() -> None:
    draft = _draft()
    with pytest.raises(ValidationError):
        draft.event_type = "OTHER"  # type: ignore[misc]


def test_draft_rejects_correlation_id_over_64_chars() -> None:
    with pytest.raises(ValidationError):
        _draft(correlation_id="x" * 65)


def test_draft_defaults_tool_calls_to_empty_list_when_omitted() -> None:
    draft = AuditEventDraft(
        correlation_id="c0ffee5678abcd",
        stage=AuditStage.INPUT,
        event_type="CHAT_MESSAGE_RECEIVED",
        actor_kind=ActorKind.CUSTOMER,
        actor_persona=Persona.CUSTOMER,
        customer_id="cus_000101",
        account_id="acc_000123",
    )
    assert draft.tool_calls == []
