"""Audit, provider, demo and evaluation infrastructure enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class AuditStage(StrEnum):
    INPUT = "INPUT"
    AI_INTERPRETATION = "AI_INTERPRETATION"
    PROPOSAL = "PROPOSAL"
    RULE_VALIDATION = "RULE_VALIDATION"
    HUMAN_DECISION = "HUMAN_DECISION"
    FINAL_STATE = "FINAL_STATE"


class ProviderMode(StrEnum):
    MOCK = "MOCK"
    LIVE = "LIVE"


class LlmMode(StrEnum):
    MOCK = "MOCK"
    LIVE = "LIVE"


class ClockMode(StrEnum):
    SYSTEM = "SYSTEM"
    SIMULATED = "SIMULATED"


class DataLabel(StrEnum):
    ILLUSTRATIVE = "ILLUSTRATIVE"
    MOCK = "MOCK"
    LIVE = "LIVE"


class ClaimStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    PASS = "PASS"
    FAIL = "FAIL"


class KpiUnit(StrEnum):
    COUNT = "COUNT"
    CURRENCY = "CURRENCY"
    RATIO = "RATIO"
    MILLISECONDS = "MILLISECONDS"
    USD_ESTIMATE = "USD_ESTIMATE"


class CaseSummaryKind(StrEnum):
    NONE = "NONE"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    HANDOFF_FAILED = "HANDOFF_FAILED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
