"""Persona and actor-identity enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class Persona(StrEnum):
    CUSTOMER = "CUSTOMER"
    COLLECTIONS_OFFICER = "COLLECTIONS_OFFICER"
    COLLECTIONS_MANAGER = "COLLECTIONS_MANAGER"
    COMPLIANCE_RISK = "COMPLIANCE_RISK"


class ActorKind(StrEnum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    SYSTEM = "SYSTEM"
    AI = "AI"


class ReviewerRole(StrEnum):
    COLLECTIONS_OFFICER = "COLLECTIONS_OFFICER"
    COMPLIANCE_RISK = "COMPLIANCE_RISK"


class CaseSource(StrEnum):
    AI = "AI"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"
    REVIEWER = "REVIEWER"
