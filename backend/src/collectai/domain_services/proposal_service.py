"""Proposal persistence (E6-S2, E6-S3; data-models.md Proposal, D-041).

A `Proposal` row is the customer-visible, deterministic record of "what will
happen if the customer confirms" -- created only here, from already
rules-engine-validated terms, never from the LLM's own words (CLAUDE.md's
core engineering principle). `application._chat_proposal_flow` is this
module's only caller for creation; `application.confirmation_flow` is its
only caller for revalidation/consumption at confirm/cancel time.

Only `PTP` and `PAYMENT` proposal kinds are created in this group
(E6-S2/E6-S3); `ARRANGEMENT` (E8-S1) and `EXCEPTION_REQUEST` (E7-S4) are
Slice-2 kinds this module's `terms_hash`/wire-shape helpers are written
generically enough to support later without a breaking change, but no
constructor for them exists yet.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.proposal import ProposalOrm
from collectai.persistence.repositories.proposal_repository import ProposalRepository
from collectai.types.clock import Clock
from collectai.types.enums import PayableOptionType, ProposalKind, ProposalStatus
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.money import Money

SIMULATED_PAYMENT_LABEL = "Simulated payment - no real money moves"

_proposal_repository = ProposalRepository()


def compute_terms_hash(terms: dict[str, Any]) -> str:
    """sha256 hex of the canonical (sorted-key) JSON of `terms` (data-models.md
    `Proposal.terms_hash`): the confirm request echoes this back, so the
    customer can only confirm terms exactly as displayed."""
    canonical = json.dumps(terms, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ptp_terms(*, promised_amount: Money, promised_date: str) -> dict[str, Any]:
    return {
        "kind": ProposalKind.PTP.value,
        "promised_amount": promised_amount.to_api_string(),
        "promised_date": promised_date,
    }


def payment_terms(
    *, payment_option: PayableOptionType, payment_amount: Money
) -> dict[str, Any]:
    return {
        "kind": ProposalKind.PAYMENT.value,
        "payment_option": payment_option.value,
        "payment_amount": payment_amount.to_api_string(),
        "simulated": True,
        "simulated_label": SIMULATED_PAYMENT_LABEL,
    }


async def _supersede_pending(session: AsyncSession, conversation_id: str) -> None:
    """AC (data-models.md): "A snapshot refresh sets pending proposals
    INVALIDATED" -- the same rule applies whenever a new proposal is about to
    take the one-pending-per-conversation slot: the previous PENDING_CONFIRMATION
    proposal (if any, e.g. the customer changed their mind mid-conversation
    without cancelling first) is invalidated rather than left dangling, so the
    unique partial index is never violated."""
    existing = await _proposal_repository.get_pending_by_conversation(session, conversation_id)
    if existing is not None:
        existing.status = ProposalStatus.INVALIDATED.value
        await session.flush()


async def create_proposal(
    session: AsyncSession,
    *,
    conversation_id: str,
    customer_id: str,
    account_id: str,
    kind: ProposalKind,
    terms: dict[str, Any],
    summary: str,
    simulated: bool,
    record_version: int,
    policy_version: str,
    clock: Clock,
    proposal_ttl_minutes: int,
) -> ProposalOrm:
    """Insert a new PENDING_CONFIRMATION proposal, superseding any prior
    pending proposal for the same conversation first (AC1: only the explicit
    confirm action, never the initial statement, creates a PTP/PaymentEvent --
    this only ever creates the *offer*, not the resource itself)."""
    await _supersede_pending(session, conversation_id)
    now = clock.now()
    row = ProposalOrm(
        proposal_id=generate_id(EntityPrefix.PROPOSAL),
        conversation_id=conversation_id,
        case_id=None,
        customer_id=customer_id,
        account_id=account_id,
        kind=kind.value,
        status=ProposalStatus.PENDING_CONFIRMATION.value,
        terms=terms,
        terms_hash=compute_terms_hash(terms),
        summary=summary,
        simulated=simulated,
        record_version=record_version,
        policy_version=policy_version,
        created_at=now,
        expires_at=now + timedelta(minutes=proposal_ttl_minutes),
        confirmed_at=None,
        resulting_resource_id=None,
    )
    session.add(row)
    await session.flush()
    return row


def is_expired(row: ProposalOrm, *, now: datetime) -> bool:
    return now > row.expires_at


def to_wire(row: ProposalOrm) -> dict[str, Any]:
    """`Proposal` API shape (api-contracts.md section 4)."""
    return {
        "proposal_id": row.proposal_id,
        "conversation_id": row.conversation_id,
        "kind": row.kind,
        "status": row.status,
        "terms": row.terms,
        "terms_hash": row.terms_hash,
        "summary": row.summary,
        "simulated": row.simulated,
        "record_version": row.record_version,
        "created_at": _iso_z(row.created_at),
        "expires_at": _iso_z(row.expires_at),
    }


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
