"""Contact, interaction and suppression enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class ContactOutcome(StrEnum):
    NO_CONTACT = "NO_CONTACT"
    CONTACT_NO_COMMITMENT = "CONTACT_NO_COMMITMENT"
    PTP_MADE = "PTP_MADE"
    PTP_BROKEN = "PTP_BROKEN"
    PAYMENT_MADE = "PAYMENT_MADE"


class InteractionChannel(StrEnum):
    SIMULATED_CHAT = "SIMULATED_CHAT"
    SIMULATED_OUTBOUND_CALL = "SIMULATED_OUTBOUND_CALL"
    SIMULATED_OUTBOUND_MESSAGE = "SIMULATED_OUTBOUND_MESSAGE"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class InteractionDirection(StrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    INTERNAL = "INTERNAL"


class SuppressionSource(StrEnum):
    ESCALATION = "ESCALATION"
    HARDSHIP = "HARDSHIP"
    DISPUTE = "DISPUTE"
    VULNERABLE = "VULNERABLE"


class SuppressionScope(StrEnum):
    ITEM = "ITEM"
    ACCOUNT = "ACCOUNT"


class Freshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
