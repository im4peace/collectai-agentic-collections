"""PTP, payment, arrangement and proposal enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class PtpStatus(StrEnum):
    PENDING = "PENDING"
    KEPT = "KEPT"
    BROKEN = "BROKEN"
    CANCELLED = "CANCELLED"


class PtpSource(StrEnum):
    OFFICER_MANUAL = "OFFICER_MANUAL"
    CUSTOMER_CHAT = "CUSTOMER_CHAT"


class PaymentOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PaymentSource(StrEnum):
    CUSTOMER_CHAT = "CUSTOMER_CHAT"
    DEMO_CONTROL = "DEMO_CONTROL"


class PayableOptionType(StrEnum):
    OVERDUE_AMOUNT = "OVERDUE_AMOUNT"
    FULL_BALANCE = "FULL_BALANCE"


class ArrangementStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ArrangementCreatedVia(StrEnum):
    CUSTOMER_CONFIRMATION = "CUSTOMER_CONFIRMATION"
    EXCEPTION_APPROVAL = "EXCEPTION_APPROVAL"


class ProposalKind(StrEnum):
    PTP = "PTP"
    PAYMENT = "PAYMENT"
    ARRANGEMENT = "ARRANGEMENT"
    EXCEPTION_REQUEST = "EXCEPTION_REQUEST"


class ProposalStatus(StrEnum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
