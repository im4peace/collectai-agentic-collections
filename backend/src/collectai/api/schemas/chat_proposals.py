"""Proposal/confirm/cancel/handoff wire schemas (E6-S2, E6-S3, E7-S1;
api-contracts.md section 4: `Proposal`, `ConfirmRequest`, `ConfirmOutcome`,
`ConfirmResult`, `CancelProposalResult`, `HandoffRequest`, `HandoffResult`).

Split out of `api/schemas/chat.py` to keep that module under the code-gen
skill's 300-line block threshold; `chat.py`'s `ChatTurnResponse.proposal`
and `ConversationDetail.pending_proposal` import `Proposal` from here.

`terms` is typed as a plain JSON object (`dict[str, Any]`), matching the
same "per-kind variant object" convention `types.models.escalation_case
.EscalationCase.requested_terms` already uses, rather than a discriminated
Pydantic union -- the four `*Terms` shapes api-contracts.md documents
(`PtpTerms`, `PaymentTerms`, `ArrangementTerms`, `ExceptionRequestTerms`)
are discriminated by `terms["kind"]` on the wire; only `PtpTerms` and
`PaymentTerms` are ever produced in this group (E6-S2/E6-S3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from collectai.api.schemas._chat_message import ChatMessage
from collectai.api.schemas.me import EscalationCustomerView, PaymentArrangement, PaymentEvent
from collectai.api.schemas.me import PromiseToPay as MePromiseToPay
from collectai.types.enums import ProposalKind, ProposalStatus

__all__ = [
    "CancelProposalResult",
    "ConfirmOutcome",
    "ConfirmRequest",
    "ConfirmResult",
    "HandoffRequest",
    "HandoffResult",
    "Proposal",
]


class Proposal(BaseModel):
    """A deterministic, customer-visible proposal awaiting explicit
    confirmation (D-041)."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    conversation_id: str | None
    kind: ProposalKind
    status: ProposalStatus
    terms: dict[str, Any]
    terms_hash: str
    summary: str
    simulated: bool
    record_version: int
    created_at: datetime
    expires_at: datetime


class ConfirmRequest(BaseModel):
    """Explicit customer confirmation of a displayed proposal. Unknown
    fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    terms_hash: str = Field(min_length=1)


class ConfirmOutcome(BaseModel):
    """What the domain service created (exactly one non-null field)."""

    model_config = ConfigDict(frozen=True)

    kind: ProposalKind
    ptp: MePromiseToPay | None = None
    payment_event: PaymentEvent | None = None
    arrangement: PaymentArrangement | None = None
    escalation: EscalationCustomerView | None = None


class ConfirmResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal: Proposal | None
    outcome: ConfirmOutcome
    assistant_message: ChatMessage
    replayed: bool


class CancelProposalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal: Proposal
    assistant_message: ChatMessage


class HandoffRequest(BaseModel):
    """Talk to a human. Unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class HandoffResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    escalation: EscalationCustomerView
    assistant_message: ChatMessage
    replayed: bool
