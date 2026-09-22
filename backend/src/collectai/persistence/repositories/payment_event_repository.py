"""PaymentEvent repository (customer-owned, AC6). Insert-only in production
(no UPDATE grant, data-models.md PaymentEvent) — this repository exposes no
update method."""

from __future__ import annotations

from collectai.persistence.orm.payment_event import PaymentEventOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class PaymentEventRepository(CustomerScopedRepository[PaymentEventOrm]):
    def __init__(self) -> None:
        super().__init__(PaymentEventOrm)
