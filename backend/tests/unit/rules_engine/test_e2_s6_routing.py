"""E2-S6 Escalation routing service tests.

Covers all five acceptance criteria for `collectai.rules_engine.routing`:
AC1 (per-reason contract mapping), AC2 (unrecognized/missing reason fails
closed to the policy's own fallback), AC3 (minimal signature + result
shape), AC4 (priority floor + determinism), AC5 (policy-unavailable
fail-closed to the hardcoded destination, never an empty routing).
"""

from __future__ import annotations

import inspect

import pytest

from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.routing import RoutingResult, route_escalation
from collectai.types.enums import EscalationPriority, EscalationReason, ReviewerRole, ReviewQueue

# AC1: the contract's exact reason -> (queue, reviewer_role) mapping.
_CONTRACT_DESTINATIONS: dict[EscalationReason, tuple[ReviewQueue, ReviewerRole]] = {
    EscalationReason.REQUEST_HUMAN: (
        ReviewQueue.COLLECTIONS_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.UNRESOLVED_UNKNOWN: (
        ReviewQueue.COLLECTIONS_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.AI_FAILURE_FALLBACK: (
        ReviewQueue.COLLECTIONS_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.SETTLEMENT_REQUEST: (
        ReviewQueue.COLLECTIONS_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.AMBIGUOUS_VALIDATION: (
        ReviewQueue.COLLECTIONS_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.EXCEPTIONAL_ARRANGEMENT: (
        ReviewQueue.COLLECTIONS_EXCEPTION_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.FINANCIAL_HARDSHIP: (
        ReviewQueue.HARDSHIP_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.DISPUTE: (
        ReviewQueue.DISPUTE_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.VULNERABLE_CUSTOMER: (
        ReviewQueue.VULNERABLE_CUSTOMER_REVIEW,
        ReviewerRole.COLLECTIONS_OFFICER,
    ),
    EscalationReason.POLICY_EXCEPTION: (
        ReviewQueue.COMPLIANCE_REVIEW,
        ReviewerRole.COMPLIANCE_RISK,
    ),
    EscalationReason.HIGH_RISK_COMPLIANCE: (
        ReviewQueue.COMPLIANCE_REVIEW,
        ReviewerRole.COMPLIANCE_RISK,
    ),
}


# --- AC1 ---------------------------------------------------------------


@pytest.mark.parametrize("reason", list(EscalationReason))
def test_each_of_the_eleven_reasons_routes_to_its_contract_destination(
    reason: EscalationReason, active_policy_provider: PolicyProvider
) -> None:
    expected_queue, expected_reviewer_role = _CONTRACT_DESTINATIONS[reason]

    result = route_escalation(reason, active_policy_provider)

    assert result.queue == expected_queue
    assert result.reviewer_role == expected_reviewer_role
    assert result.reason == reason
    assert result.flags == []


def test_all_eleven_escalation_reasons_are_covered_by_the_contract_table() -> None:
    """Guards against the mapping table above silently drifting out of sync."""
    assert set(_CONTRACT_DESTINATIONS) == set(EscalationReason)
    assert len(_CONTRACT_DESTINATIONS) == 11


# --- AC2 -----------------------------------------------------------------


def test_unrecognized_reason_string_fails_closed_to_policy_fallback(
    active_policy_provider: PolicyProvider,
) -> None:
    result = route_escalation("NOT_A_REAL_REASON", active_policy_provider)

    assert result.queue == ReviewQueue.COLLECTIONS_REVIEW
    assert result.reviewer_role == ReviewerRole.COLLECTIONS_OFFICER
    assert result.flags == ["reason_unrecognized"]
    assert result.reason is None


def test_missing_reason_fails_closed_to_policy_fallback(
    active_policy_provider: PolicyProvider,
) -> None:
    result = route_escalation(None, active_policy_provider)

    assert result.queue == ReviewQueue.COLLECTIONS_REVIEW
    assert result.reviewer_role == ReviewerRole.COLLECTIONS_OFFICER
    assert result.flags == ["reason_unrecognized"]
    assert result.reason is None


# --- AC3 -----------------------------------------------------------------


def test_signature_accepts_only_reason_and_policy_provider() -> None:
    parameter_names = set(inspect.signature(route_escalation).parameters)

    assert parameter_names == {"reason", "policy_provider"}
    assert "queue" not in parameter_names
    assert "reviewer_role" not in parameter_names


def test_result_carries_reason_queue_reviewer_role_priority_and_policy_version(
    active_policy_provider: PolicyProvider,
) -> None:
    result = route_escalation(EscalationReason.DISPUTE, active_policy_provider)

    assert isinstance(result, RoutingResult)
    assert result.reason == EscalationReason.DISPUTE
    assert result.queue == ReviewQueue.DISPUTE_REVIEW
    assert result.reviewer_role == ReviewerRole.COLLECTIONS_OFFICER
    assert result.priority == EscalationPriority.ELEVATED
    assert result.policy_version == "policy-v1"


# --- AC4 -----------------------------------------------------------------


@pytest.mark.parametrize(
    "reason", [EscalationReason.VULNERABLE_CUSTOMER, EscalationReason.FINANCIAL_HARDSHIP]
)
def test_vulnerable_customer_and_financial_hardship_receive_at_least_elevated_priority(
    reason: EscalationReason, active_policy_provider: PolicyProvider
) -> None:
    result = route_escalation(reason, active_policy_provider)

    assert result.priority in (EscalationPriority.ELEVATED, EscalationPriority.URGENT)


def test_identical_inputs_always_return_the_identical_priority(
    active_policy_provider: PolicyProvider,
) -> None:
    first = route_escalation(EscalationReason.FINANCIAL_HARDSHIP, active_policy_provider)
    second = route_escalation(EscalationReason.FINANCIAL_HARDSHIP, active_policy_provider)

    assert first.priority == second.priority


# --- AC5 -----------------------------------------------------------------


def test_no_active_policy_falls_back_to_hardcoded_collections_review() -> None:
    provider = PolicyProvider()

    result = route_escalation(EscalationReason.DISPUTE, provider)

    assert result is not None
    assert result.queue == ReviewQueue.COLLECTIONS_REVIEW
    assert result.reviewer_role == ReviewerRole.COLLECTIONS_OFFICER
    assert result.policy_version is None
    assert result.flags == ["POLICY_UNAVAILABLE"]


def test_policy_unavailable_never_raises_and_never_returns_none() -> None:
    provider = PolicyProvider()

    result = route_escalation(EscalationReason.VULNERABLE_CUSTOMER, provider)

    assert result is not None
    assert isinstance(result, RoutingResult)


def test_policy_unavailable_preserves_recognized_reason_for_traceability() -> None:
    provider = PolicyProvider()

    result = route_escalation(EscalationReason.SETTLEMENT_REQUEST, provider)

    assert result.reason == EscalationReason.SETTLEMENT_REQUEST
