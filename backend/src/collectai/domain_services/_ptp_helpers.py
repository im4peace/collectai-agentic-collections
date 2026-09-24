"""Private lookup, construction and response-shaping helpers for
`ptp_service.py`.

Split out of `ptp_service.py` once that module neared the code-gen skill's
300-line hard block (principle #5): `ptp_service.py` keeps the public entry
points and orchestration; this module holds the data shapes it passes
around plus everything that supports it -- delinquency-record and
conflict/dispute lookups, `PromiseToPayOrm`/`AuditEventDraft` construction,
and the wire-shape dict a `PromiseToPay` API response and a stored
`idempotency_record.response_body` both use. Nothing here is a public
contract of this package; only `ptp_service.py` and `_ptp_idempotency.py`
import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.dispute import DisputeOrm
from collectai.persistence.orm.promise_to_pay import PromiseToPayOrm
from collectai.rules_engine.ptp_rules import Alternatives
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    AuditStage,
    Bucket,
    CollectionStatus,
    DisputeStatus,
    Persona,
    PtpSource,
    PtpStatus,
)
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_ZERO: Decimal = Decimal("0")

_VIOLATION_MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.ZERO_AMOUNT: "The promised amount must be greater than zero.",
    ReasonCode.NEGATIVE_AMOUNT: "The promised amount must not be negative.",
    ReasonCode.OVER_PRECISION: "The promised amount must have at most 2 decimal places.",
    ReasonCode.OVER_BALANCE: "The promised amount is more than the current overdue amount.",
    ReasonCode.BELOW_MIN_AMOUNT: "The promised amount is below the policy minimum.",
    ReasonCode.PAST_DATE: "The promised date must not be in the past.",
    ReasonCode.OUTSIDE_WINDOW: "The promised date is outside the policy's allowed window.",
    ReasonCode.FIELD_INVALID: "The promised amount is not a valid decimal value.",
}


@dataclass(frozen=True, slots=True)
class DryRunValidationResult:
    """`POST /api/ptps/validate`'s outcome, already wire-shaped."""

    valid: bool
    reason_codes: list[ReasonCode]
    alternatives: dict[str, Any] | None
    policy_version: str


@dataclass(frozen=True, slots=True)
class PtpRecordRequest:
    """The officer-submitted fields `POST /api/ptps` needs (api-contracts.md
    `PtpCreateRequest`), decoupled from the Pydantic request schema so
    `domain_services` never imports `api.schemas` (layering, see
    `ptp_service.py`'s module docstring)."""

    account_id: str
    promised_amount: str
    promised_date: date
    interaction_reference: str | None
    item_id: str | None
    record_version: int
    snapshot_as_of: datetime


@dataclass(frozen=True, slots=True)
class RecordPtpOutcome:
    response_body: dict[str, Any]
    replayed: bool


async def get_delinquency_record(
    session: AsyncSession, account_id: str
) -> DelinquencyRecordOrm | None:
    """The account's `delinquency_record` row, unscoped by customer: officer
    endpoints operate on any account, unlike a CUSTOMER's own `/api/me/*`
    lookups (api-contracts.md 1.5's object-level check does not apply here)."""
    stmt = select(DelinquencyRecordOrm).where(DelinquencyRecordOrm.account_id == account_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def to_domain_record(row: DelinquencyRecordOrm) -> DelinquencyRecord:
    return DelinquencyRecord(
        account_id=row.account_id,
        customer_id=row.customer_id,
        outstanding_balance=row.outstanding_balance,
        overdue_amount=row.overdue_amount,
        dpd=row.dpd,
        bucket=Bucket(row.bucket),
        collection_status=CollectionStatus(row.collection_status),
        as_of=row.as_of,
        record_version=row.record_version,
        updated_at=row.updated_at,
    )


async def has_active_pending_ptp(session: AsyncSession, account_id: str) -> bool:
    """AC4: a second PENDING PTP on the same account is a
    `CONFLICTING_ACTIVE_ITEM` conflict, not a new row."""
    stmt = (
        select(PromiseToPayOrm.ptp_id)
        .where(
            PromiseToPayOrm.account_id == account_id,
            PromiseToPayOrm.status == PtpStatus.PENDING.value,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def has_open_dispute(session: AsyncSession, *, account_id: str, item_id: str | None) -> bool:
    """AC4's `DISPUTED_ITEM` check: an item-specific dispute when `item_id`
    is given, else a whole-overdue-amount dispute (`item_id IS NULL`) on the
    account -- never an unrelated item's dispute (CLAUDE.md: suppression and
    disputes never block more than their own scope)."""
    conditions = [
        DisputeOrm.account_id == account_id,
        DisputeOrm.status != DisputeStatus.RESOLVED.value,
    ]
    conditions.append(
        DisputeOrm.item_id == item_id if item_id is not None else DisputeOrm.item_id.is_(None)
    )
    stmt = select(DisputeOrm.dispute_id).where(*conditions).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def alternatives_to_dict(alternatives: Alternatives | None) -> dict[str, Any] | None:
    """Map `rules_engine.ptp_rules.Alternatives` to the wire shape
    (api-contracts.md `PtpValidationResult.alternatives` /
    `ErrorEnvelope.error.alternatives`)."""
    if alternatives is None:
        return None
    result: dict[str, Any] = {}
    if alternatives.valid_amount_range is not None:
        result["valid_amount_range"] = {
            "min": alternatives.valid_amount_range.min.to_api_string(),
            "max": alternatives.valid_amount_range.max.to_api_string(),
        }
    if alternatives.valid_date_range is not None:
        result["valid_date_range"] = {
            "earliest": alternatives.valid_date_range.earliest.isoformat(),
            "latest": alternatives.valid_date_range.latest.isoformat(),
        }
    return result or None


def business_violation_message(reason_code: ReasonCode) -> str:
    return _VIOLATION_MESSAGES.get(reason_code, "The promised amount or date failed validation.")


def build_ptp_row(
    request: PtpRecordRequest,
    customer_id: str,
    policy_version: str,
    clock: Clock,
    *,
    source: PtpSource = PtpSource.OFFICER_MANUAL,
    created_by_persona: Persona = Persona.COLLECTIONS_OFFICER,
) -> PromiseToPayOrm:
    """`source`/`created_by_persona` default to the E6-S6 officer-manual
    workflow's values; E6-S2's chat-driven path passes `PtpSource.CUSTOMER_CHAT`
    / `Persona.CUSTOMER` explicitly (see `record_chat_ptp` in
    `ptp_service.py`)."""
    now = clock.now()
    return PromiseToPayOrm(
        ptp_id=generate_id(EntityPrefix.PROMISE_TO_PAY),
        account_id=request.account_id,
        customer_id=customer_id,
        item_id=request.item_id,
        promised_amount=Money(request.promised_amount),
        promised_date=request.promised_date,
        status=PtpStatus.PENDING.value,
        cumulative_paid=Money("0"),
        interaction_reference=request.interaction_reference,
        source=source.value,
        created_by_persona=created_by_persona.value,
        created_at=now,
        updated_at=now,
        policy_version=policy_version,
        version=1,
    )


def build_audit_draft(
    row: PromiseToPayOrm, correlation_id: str, persona: Persona
) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.FINAL_STATE,
        event_type="PTP_RECORDED",
        actor_kind=ActorKind.STAFF,
        actor_persona=persona,
        customer_id=row.customer_id,
        account_id=row.account_id,
        capability="ptp:record",
        policy_version=row.policy_version,
        final_action="POST /api/ptps",
        resource_type="promise_to_pay",
        resource_id=row.ptp_id,
    )


def ptp_wire_dict(row: PromiseToPayOrm) -> dict[str, Any]:
    """The `PromiseToPay` API shape (api-contracts.md section 4) as a plain,
    JSON-safe dict: used both for the HTTP response body (via
    `PromiseToPayResponse.model_validate`) and as the stored
    `idempotency_record.response_body` a replay later re-validates the same
    way, so the two never drift apart."""
    remaining = Money(max(row.promised_amount.amount - row.cumulative_paid.amount, _ZERO))
    return {
        "ptp_id": row.ptp_id,
        "account_id": row.account_id,
        "promised_amount": row.promised_amount.to_api_string(),
        "promised_date": row.promised_date.isoformat(),
        "status": row.status,
        "cumulative_paid": row.cumulative_paid.to_api_string(),
        "remaining_amount": remaining.to_api_string(),
        "interaction_reference": row.interaction_reference,
        "source": row.source,
        "created_by_persona": row.created_by_persona,
        "created_at": _iso_z(row.created_at),
        "updated_at": _iso_z(row.updated_at),
        "kept_at": _iso_z(row.kept_at) if row.kept_at else None,
        "broken_at": _iso_z(row.broken_at) if row.broken_at else None,
        "cancelled_at": _iso_z(row.cancelled_at) if row.cancelled_at else None,
        "cancel_reason": row.cancel_reason,
        "policy_version": row.policy_version,
        "version": row.version,
    }


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
