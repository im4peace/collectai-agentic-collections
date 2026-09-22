"""Tests for collectai.types.enums (E1-S1 AC4, AC5).

Every enum in api-contracts.md section 5 is exercised by the parametrized
round-trip test at the bottom of this file. The AC-named enums additionally
get focused tests asserting that an out-of-catalogue value is rejected.
"""

from __future__ import annotations

import pytest

from collectai.types import enums
from collectai.types.enums import (
    AccountType,
    EscalationReason,
    Intent,
    PtpStatus,
    ReviewerRole,
    ReviewQueue,
)

# name -> expected members, exactly as listed in api-contracts.md section 5
ENUM_MEMBERS: dict[str, list[str]] = {
    "Persona": ["CUSTOMER", "COLLECTIONS_OFFICER", "COLLECTIONS_MANAGER", "COMPLIANCE_RISK"],
    "AccountType": ["CARD", "PERSONAL_LOAN"],
    "Bucket": ["CURRENT", "DPD_1_29", "DPD_30_59", "DPD_60_89", "DPD_90_PLUS"],
    "CollectionStatus": [
        "NEW",
        "IN_PROGRESS",
        "PTP_PENDING",
        "ARRANGEMENT_ACTIVE",
        "ESCALATED",
        "RESOLVED",
    ],
    "PriorityBand": ["LOW", "MEDIUM", "HIGH"],
    "Intent": [
        "PAY_NOW",
        "PROMISE_TO_PAY",
        "PAYMENT_PLAN",
        "FINANCIAL_HARDSHIP",
        "DISPUTE",
        "REQUEST_HUMAN",
        "UNKNOWN",
    ],
    "SpecialRequest": ["NONE", "SETTLEMENT", "POLICY_EXCEPTION"],
    "VulnerabilityCategory": [
        "BEREAVEMENT",
        "SERIOUS_ILLNESS_OR_DISABILITY",
        "MENTAL_HEALTH_CONCERN",
        "DOMESTIC_ABUSE_OR_COERCION",
        "LIMITED_CAPACITY_TO_UNDERSTAND",
        "LANGUAGE_OR_COMMUNICATION_BARRIER",
        "OTHER",
    ],
    "PtpStatus": ["PENDING", "KEPT", "BROKEN", "CANCELLED"],
    "PtpSource": ["OFFICER_MANUAL", "CUSTOMER_CHAT"],
    "PaymentOutcome": ["SUCCEEDED", "FAILED"],
    "PaymentSource": ["CUSTOMER_CHAT", "DEMO_CONTROL"],
    "PayableOptionType": ["OVERDUE_AMOUNT", "FULL_BALANCE"],
    "ArrangementStatus": ["ACTIVE", "COMPLETED", "CANCELLED"],
    "ArrangementCreatedVia": ["CUSTOMER_CONFIRMATION", "EXCEPTION_APPROVAL"],
    "EscalationReason": [
        "REQUEST_HUMAN",
        "UNRESOLVED_UNKNOWN",
        "AI_FAILURE_FALLBACK",
        "EXCEPTIONAL_ARRANGEMENT",
        "FINANCIAL_HARDSHIP",
        "DISPUTE",
        "SETTLEMENT_REQUEST",
        "AMBIGUOUS_VALIDATION",
        "VULNERABLE_CUSTOMER",
        "POLICY_EXCEPTION",
        "HIGH_RISK_COMPLIANCE",
    ],
    "ReviewQueue": [
        "COLLECTIONS_REVIEW",
        "COLLECTIONS_EXCEPTION_REVIEW",
        "HARDSHIP_REVIEW",
        "DISPUTE_REVIEW",
        "VULNERABLE_CUSTOMER_REVIEW",
        "COMPLIANCE_REVIEW",
    ],
    "ReviewerRole": ["COLLECTIONS_OFFICER", "COMPLIANCE_RISK"],
    "EscalationPriority": ["NORMAL", "ELEVATED", "URGENT"],
    "CaseStatus": ["OPEN", "IN_REVIEW", "AWAITING_INFORMATION", "DECIDED", "RE_ROUTED"],
    "CaseSource": ["AI", "CUSTOMER", "SYSTEM", "REVIEWER"],
    "ReviewAction": ["APPROVE", "REJECT", "MODIFY", "REQUEST_MORE_INFORMATION", "ESCALATE"],
    "DecisionKind": ["REVIEWER_ACTION", "COMPLIANCE_DECISION", "START_REVIEW"],
    "ComplianceOutcome": ["CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED"],
    "ExceptionType": ["TERM", "START_DATE", "AMOUNT_STRUCTURE"],
    "EligibilityClass": ["ELIGIBLE", "EXCEPTIONAL", "NOT_ELIGIBLE"],
    "HardshipIndicatorType": [
        "JOB_LOSS",
        "INCOME_REDUCTION",
        "MEDICAL_OR_FAMILY_EMERGENCY",
        "TEMPORARY_FINANCIAL_DIFFICULTY",
        "OTHER",
    ],
    "HardshipStatus": ["OPEN", "UNDER_REVIEW", "DECIDED"],
    "DisputeCategory": [
        "AMOUNT_INCORRECT",
        "NOT_MY_DEBT",
        "ALREADY_PAID",
        "FRAUD_OR_UNAUTHORIZED",
        "FEE_OR_INTEREST_DISPUTE",
        "OTHER",
    ],
    "DisputeStatus": ["OPEN", "UNDER_REVIEW", "RESOLVED"],
    "DisputeOutcome": ["UPHELD", "REJECTED", "WITHDRAWN"],
    "NbaAction": [
        "CONTACT_CUSTOMER",
        "REQUEST_PAYMENT",
        "OFFER_ELIGIBLE_ARRANGEMENT",
        "FOLLOW_UP_PTP",
        "REFER_TO_HARDSHIP_WORKFLOW",
        "ESCALATE_TO_HUMAN_REVIEW",
    ],
    "RecommendationStatus": [
        "GENERATED",
        "SAFE_FALLBACK",
        "HUMAN_REVIEW_ONLY",
        "AI_UNAVAILABLE",
        "NOT_GENERATED",
    ],
    "RecommendationDecision": ["ACCEPTED", "OVERRIDDEN"],
    "ContentSource": ["MODEL", "TEMPLATE", "CUSTOMER_INPUT"],
    "ProposalKind": ["PTP", "PAYMENT", "ARRANGEMENT", "EXCEPTION_REQUEST"],
    "ProposalStatus": [
        "PENDING_CONFIRMATION",
        "CONFIRMED",
        "CANCELLED",
        "EXPIRED",
        "INVALIDATED",
    ],
    "MessageRole": ["CUSTOMER", "ASSISTANT", "SYSTEM"],
    "ConversationStatus": ["ACTIVE", "HANDED_OFF", "CLOSED"],
    "SafeState": [
        "NONE",
        "AI_UNAVAILABLE",
        "HANDOFF_CREATED",
        "HANDOFF_FAILED",
        "POLICY_UNAVAILABLE",
        "AUDIT_UNAVAILABLE",
        "TOOL_CAP_REACHED",
        "STALE_DATA_REFRESHED",
    ],
    "MessageLabel": ["AI_DISCLOSURE", "SIMULATED", "HUMAN_HANDOFF", "SAFE_FALLBACK"],
    "Freshness": ["FRESH", "STALE", "UNKNOWN"],
    "ItemKind": ["INSTALLMENT", "STATEMENT_CYCLE", "FEE_OR_CHARGE"],
    "ItemStatus": ["OPEN", "PAID"],
    "ContactOutcome": [
        "NO_CONTACT",
        "CONTACT_NO_COMMITMENT",
        "PTP_MADE",
        "PTP_BROKEN",
        "PAYMENT_MADE",
    ],
    "InteractionChannel": [
        "SIMULATED_CHAT",
        "SIMULATED_OUTBOUND_CALL",
        "SIMULATED_OUTBOUND_MESSAGE",
        "SYSTEM_EVENT",
    ],
    "InteractionDirection": ["INBOUND", "OUTBOUND", "INTERNAL"],
    "SuppressionSource": ["ESCALATION", "HARDSHIP", "DISPUTE", "VULNERABLE"],
    "SuppressionScope": ["ITEM", "ACCOUNT"],
    "AuditStage": [
        "INPUT",
        "AI_INTERPRETATION",
        "PROPOSAL",
        "RULE_VALIDATION",
        "HUMAN_DECISION",
        "FINAL_STATE",
    ],
    "ActorKind": ["CUSTOMER", "STAFF", "SYSTEM", "AI"],
    "ProviderMode": ["MOCK", "LIVE"],
    "LlmMode": ["MOCK", "LIVE"],
    "ClockMode": ["SYSTEM", "SIMULATED"],
    "DataLabel": ["ILLUSTRATIVE", "MOCK", "LIVE"],
    "ClaimStatus": ["NOT_APPLICABLE", "OBSERVATION_ONLY", "PASS", "FAIL"],
    "KpiUnit": ["COUNT", "CURRENCY", "RATIO", "MILLISECONDS", "USD_ESTIMATE"],
    "CaseSummaryKind": ["NONE", "OPEN", "CLOSED"],
    "ErrorCode": [
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "NOT_FOUND",
        "VALIDATION_ERROR",
        "BUSINESS_RULE_VIOLATION",
        "CONFLICT",
        "RATE_LIMITED",
        "POLICY_UNAVAILABLE",
        "AUDIT_UNAVAILABLE",
        "HANDOFF_FAILED",
        "SERVICE_UNAVAILABLE",
        "INTERNAL_ERROR",
    ],
}


@pytest.mark.parametrize("enum_name", sorted(ENUM_MEMBERS))
def test_every_enum_member_round_trips_through_its_own_value(enum_name: str) -> None:
    enum_cls = getattr(enums, enum_name)
    expected_names = ENUM_MEMBERS[enum_name]

    assert [member.name for member in enum_cls] == expected_names
    for name in expected_names:
        member = enum_cls[name]
        assert enum_cls(member.value) is member


def test_account_type_accepts_only_card_or_personal_loan() -> None:
    assert AccountType("CARD") is AccountType.CARD
    assert AccountType("PERSONAL_LOAN") is AccountType.PERSONAL_LOAN
    with pytest.raises(ValueError):
        AccountType("SAVINGS")


def test_ptp_status_rejects_any_value_outside_the_four_statuses() -> None:
    for value in ("PENDING", "KEPT", "BROKEN", "CANCELLED"):
        assert PtpStatus(value).value == value
    with pytest.raises(ValueError):
        PtpStatus("EXPIRED")


def test_intent_labels_reject_any_value_outside_the_catalogue() -> None:
    expected = {
        "PAY_NOW",
        "PROMISE_TO_PAY",
        "PAYMENT_PLAN",
        "FINANCIAL_HARDSHIP",
        "DISPUTE",
        "REQUEST_HUMAN",
        "UNKNOWN",
    }
    assert {member.value for member in Intent} == expected
    with pytest.raises(ValueError):
        Intent("NOT_A_REAL_INTENT")


def test_vulnerable_customer_is_not_an_accepted_intent_label() -> None:
    assert "VULNERABLE_CUSTOMER" not in {member.value for member in Intent}
    with pytest.raises(ValueError):
        Intent("VULNERABLE_CUSTOMER")


def test_escalation_reason_accepts_exactly_the_eleven_contract_reasons() -> None:
    expected = {
        "REQUEST_HUMAN",
        "UNRESOLVED_UNKNOWN",
        "AI_FAILURE_FALLBACK",
        "EXCEPTIONAL_ARRANGEMENT",
        "FINANCIAL_HARDSHIP",
        "DISPUTE",
        "SETTLEMENT_REQUEST",
        "AMBIGUOUS_VALIDATION",
        "VULNERABLE_CUSTOMER",
        "POLICY_EXCEPTION",
        "HIGH_RISK_COMPLIANCE",
    }
    assert {member.value for member in EscalationReason} == expected
    assert len(expected) == 11
    with pytest.raises(ValueError):
        EscalationReason("NOT_A_REAL_REASON")


def test_review_queue_rejects_any_value_outside_the_six_queues() -> None:
    expected = {
        "COLLECTIONS_REVIEW",
        "COLLECTIONS_EXCEPTION_REVIEW",
        "HARDSHIP_REVIEW",
        "DISPUTE_REVIEW",
        "VULNERABLE_CUSTOMER_REVIEW",
        "COMPLIANCE_REVIEW",
    }
    assert {member.value for member in ReviewQueue} == expected
    with pytest.raises(ValueError):
        ReviewQueue("GENERAL_REVIEW")


def test_reviewer_role_rejects_any_value_outside_officer_or_compliance() -> None:
    assert {member.value for member in ReviewerRole} == {
        "COLLECTIONS_OFFICER",
        "COMPLIANCE_RISK",
    }
    with pytest.raises(ValueError):
        ReviewerRole("COLLECTIONS_MANAGER")
