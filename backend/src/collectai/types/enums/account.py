"""Account, delinquency and delinquent-item enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class AccountType(StrEnum):
    CARD = "CARD"
    PERSONAL_LOAN = "PERSONAL_LOAN"


class Bucket(StrEnum):
    CURRENT = "CURRENT"
    DPD_1_29 = "DPD_1_29"
    DPD_30_59 = "DPD_30_59"
    DPD_60_89 = "DPD_60_89"
    DPD_90_PLUS = "DPD_90_PLUS"


class CollectionStatus(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    PTP_PENDING = "PTP_PENDING"
    ARRANGEMENT_ACTIVE = "ARRANGEMENT_ACTIVE"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class PriorityBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ItemKind(StrEnum):
    INSTALLMENT = "INSTALLMENT"
    STATEMENT_CYCLE = "STATEMENT_CYCLE"
    FEE_OR_CHARGE = "FEE_OR_CHARGE"


class ItemStatus(StrEnum):
    OPEN = "OPEN"
    PAID = "PAID"
