"""PromiseToPay repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class PromiseToPayRepository(CustomerScopedRepository[PromiseToPayOrm]):
    def __init__(self) -> None:
        super().__init__(PromiseToPayOrm)
