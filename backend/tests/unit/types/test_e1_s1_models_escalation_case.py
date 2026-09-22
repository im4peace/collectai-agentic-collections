"""Tests for the EscalationCase domain model (data-models.md EscalationCase, AC5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from collectai.types.enums import (
    CaseSource,
    CaseStatus,
    EscalationPriority,
    EscalationReason,
    ReviewerRole,
    ReviewQueue,
)
from collectai.types.models import EscalationCase


def _case(**overrides: object) -> EscalationCase:
    fields: dict[str, object] = {
        "case_id": "esc_01J9B1C2D4",
        "customer_id": "cus_000101",
        "account_id": "acc_000123",
        "conversation_id": "conv_01J8ZK4A9B",
        "item_id": None,
        "reason": EscalationReason.FINANCIAL_HARDSHIP,
        "queue": ReviewQueue.HARDSHIP_REVIEW,
        "reviewer_role": ReviewerRole.COLLECTIONS_OFFICER,
        "priority": EscalationPriority.ELEVATED,
        "status": CaseStatus.OPEN,
        "source": CaseSource.AI,
        "summary": "Customer reports job loss; hardship review requested.",
        "requested_terms": None,
        "exception_types": None,
        "hardship_case_id": "hsp_01J9B1C2D3",
        "dispute_id": None,
        "recommendation_id": None,
        "parent_case_id": None,
        "rerouted_to_case_id": None,
        "routing_policy_version": "policy-v1",
        "routing_flags": [],
        "first_reviewed_at": None,
        "created_at": datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
        "decided_at": None,
        "updated_at": datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
        "version": 1,
    }
    fields.update(overrides)
    return EscalationCase.model_validate(fields)


def test_escalation_reason_accepts_exactly_the_eleven_contract_reasons() -> None:
    for reason in EscalationReason:
        assert _case(reason=reason).reason is reason


def test_escalation_reason_rejects_value_outside_the_catalogue() -> None:
    with pytest.raises(ValidationError):
        _case(reason="OUT_OF_SCOPE")


def test_review_queue_rejects_value_outside_the_six_queues() -> None:
    with pytest.raises(ValidationError):
        _case(queue="GENERAL_REVIEW")


def test_reviewer_role_rejects_value_outside_officer_or_compliance() -> None:
    with pytest.raises(ValidationError):
        _case(reviewer_role="COLLECTIONS_MANAGER")


def test_escalation_case_summary_is_capped_at_500_characters() -> None:
    with pytest.raises(ValidationError):
        _case(summary="x" * 501)


def test_escalation_case_routing_flags_default_representation_is_a_list() -> None:
    case = _case(routing_flags=["POLICY_UNAVAILABLE"])
    assert case.routing_flags == ["POLICY_UNAVAILABLE"]


def test_escalation_case_optional_links_may_be_none() -> None:
    case = _case(
        conversation_id=None,
        item_id=None,
        hardship_case_id=None,
        dispute_id=None,
        recommendation_id=None,
        parent_case_id=None,
        rerouted_to_case_id=None,
    )
    assert case.dispute_id is None
    assert case.parent_case_id is None
