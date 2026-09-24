"""ChatMessage repository (customer-owned, mirrors `conversation_repository.py`)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.repositories.base import CustomerScopedRepository


class ChatMessageRepository(CustomerScopedRepository[ChatMessageOrm]):
    def __init__(self) -> None:
        super().__init__(ChatMessageOrm)

    async def list_by_conversation_for_customer(
        self, session: AsyncSession, conversation_id: str, customer_id: str
    ) -> Sequence[ChatMessageOrm]:
        """Chronological messages for `conversation_id`, additionally scoped
        by `customer_id` (AC6/AC7): a message on someone else's conversation
        is never returned even if the caller somehow guessed a valid
        `conversation_id`."""
        stmt = (
            select(ChatMessageOrm)
            .where(
                ChatMessageOrm.conversation_id == conversation_id,
                ChatMessageOrm.customer_id == customer_id,
            )
            .order_by(ChatMessageOrm.created_at)
        )
        return (await session.execute(stmt)).scalars().all()
