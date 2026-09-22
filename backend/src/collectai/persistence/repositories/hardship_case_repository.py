"""HardshipCase repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.hardship_case import HardshipCaseOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class HardshipCaseRepository(CustomerScopedRepository[HardshipCaseOrm]):
    def __init__(self) -> None:
        super().__init__(HardshipCaseOrm)
