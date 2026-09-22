"""Dispute repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class DisputeRepository(CustomerScopedRepository[DisputeOrm]):
    def __init__(self) -> None:
        super().__init__(DisputeOrm)
