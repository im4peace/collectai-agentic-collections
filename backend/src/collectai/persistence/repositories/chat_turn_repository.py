"""ChatTurn repository (customer-owned, mirrors `conversation_repository.py`)."""

from __future__ import annotations

from collectai.persistence.orm.chat_turn import ChatTurnOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class ChatTurnRepository(CustomerScopedRepository[ChatTurnOrm]):
    def __init__(self) -> None:
        super().__init__(ChatTurnOrm)
