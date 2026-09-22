"""Tests for the AuditEvent domain model (data-models.md AuditEvent)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from collectai.types.enums import ActorKind, AuditStage, Persona, ProviderMode
from collectai.types.models import AuditEvent


def _audit_event(**overrides: object) -> AuditEvent:
    fields: dict[str, object] = {
        "audit_event_id": "aud_01J9E4F5G7",
        "sequence": 1042,
        "timestamp": datetime(2026, 10, 1, 9, 10, tzinfo=UTC),
        "correlation_id": "c0ffee5678abcd",
        "stage": AuditStage.AI_INTERPRETATION,
        "event_type": "NBA_GENERATED",
        "actor_kind": ActorKind.AI,
        "actor_persona": None,
        "customer_id": "cus_000101",
        "account_id": "acc_000123",
        "capability": "NEXT_BEST_ACTION",
        "provider": "mock",
        "provider_mode": ProviderMode.MOCK,
        "model_id": "mock-model-1",
        "prompt_version": "nba-v1",
        "policy_version": "policy-v1",
        "input_ref": "ctx:acc_000123@v7",
        "ai_output": {"action": "FOLLOW_UP_PTP", "referenced_factor_ids": ["dpd"]},
        "tool_calls": [],
        "rule_results": {"human_review_only": False},
        "human_override": None,
        "final_action": "RECOMMENDATION_STORED",
        "reason_code": None,
        "resource_type": "recommendation",
        "resource_id": "rec_01J9E4F5G6",
        "latency": {"provider_latency_ms": 12, "tool_call_duration_ms": 0},
        "token_usage": None,
    }
    fields.update(overrides)
    return AuditEvent.model_validate(fields)


def test_audit_event_holds_typed_stage_and_actor_enums() -> None:
    event = _audit_event()
    assert event.stage is AuditStage.AI_INTERPRETATION
    assert event.actor_kind is ActorKind.AI


def test_audit_event_tool_calls_defaults_to_empty_list() -> None:
    event = _audit_event()
    fields_without_tool_calls = {k: v for k, v in event.model_dump().items() if k != "tool_calls"}
    rebuilt = AuditEvent.model_validate(fields_without_tool_calls)
    assert rebuilt.tool_calls == []


def test_audit_event_correlation_id_is_capped_at_64_characters() -> None:
    with pytest.raises(ValidationError):
        _audit_event(correlation_id="x" * 65)


def test_audit_event_event_type_is_capped_at_80_characters() -> None:
    with pytest.raises(ValidationError):
        _audit_event(event_type="x" * 81)


def test_audit_event_actor_persona_may_be_none_for_non_persona_actors() -> None:
    event = _audit_event(actor_kind=ActorKind.SYSTEM, actor_persona=None)
    assert event.actor_persona is None


def test_audit_event_actor_persona_accepts_a_persona_when_applicable() -> None:
    event = _audit_event(actor_kind=ActorKind.STAFF, actor_persona=Persona.COLLECTIONS_OFFICER)
    assert event.actor_persona is Persona.COLLECTIONS_OFFICER


def test_audit_event_is_append_only_by_convention_and_immutable_in_python() -> None:
    event = _audit_event()
    with pytest.raises(ValidationError):
        event.final_action = "SOMETHING_ELSE"  # type: ignore[misc]
