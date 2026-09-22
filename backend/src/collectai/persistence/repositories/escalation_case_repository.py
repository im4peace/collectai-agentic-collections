"""EscalationCase repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class EscalationCaseRepository(CustomerScopedRepository[EscalationCaseOrm]):
    def __init__(self) -> None:
        super().__init__(EscalationCaseOrm)
