"""Proposal repository (customer-owned, AC6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.proposal import ProposalOrm
from collectai.persistence.repositories.base import CustomerScopedRepository
from collectai.types.enums import ProposalStatus


class ProposalRepository(CustomerScopedRepository[ProposalOrm]):
    def __init__(self) -> None:
        super().__init__(ProposalOrm)

    async def get_by_id_for_customer(
        self, session: AsyncSession, proposal_id: str, customer_id: str
    ) -> ProposalOrm | None:
        stmt = select(ProposalOrm).where(
            ProposalOrm.proposal_id == proposal_id, ProposalOrm.customer_id == customer_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_pending_by_conversation(
        self, session: AsyncSession, conversation_id: str
    ) -> ProposalOrm | None:
        """The single PENDING_CONFIRMATION proposal for a conversation, if
        any (data-models.md's `UNIQUE (conversation_id) WHERE status =
        'PENDING_CONFIRMATION'`)."""
        stmt = select(ProposalOrm).where(
            ProposalOrm.conversation_id == conversation_id,
            ProposalOrm.status == ProposalStatus.PENDING_CONFIRMATION.value,
        )
        return (await session.execute(stmt)).scalar_one_or_none()
