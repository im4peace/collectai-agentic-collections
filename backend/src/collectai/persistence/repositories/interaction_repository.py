"""Interaction repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.interaction import InteractionOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class InteractionRepository(CustomerScopedRepository[InteractionOrm]):
    def __init__(self) -> None:
        super().__init__(InteractionOrm)
