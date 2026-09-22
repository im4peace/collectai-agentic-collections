"""PaymentArrangement repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class PaymentArrangementRepository(CustomerScopedRepository[PaymentArrangementOrm]):
    def __init__(self) -> None:
        super().__init__(PaymentArrangementOrm)
