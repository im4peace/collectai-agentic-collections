"""DelinquentItem repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.delinquency import DelinquentItemOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class DelinquentItemRepository(CustomerScopedRepository[DelinquentItemOrm]):
    def __init__(self) -> None:
        super().__init__(DelinquentItemOrm)
