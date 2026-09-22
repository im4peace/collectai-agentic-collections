"""Conversation repository (customer-owned, AC6)."""

from __future__ import annotations

from collectai.persistence.orm.conversation import ConversationOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class ConversationRepository(CustomerScopedRepository[ConversationOrm]):
    def __init__(self) -> None:
        super().__init__(ConversationOrm)
