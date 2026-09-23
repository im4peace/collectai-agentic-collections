"""Private `Idempotency-Key` storage for `POST /api/ptps` (E6-S6 AC4).

Split out of `ptp_service.py` purely to respect the code-gen skill's
300-line hard block once the full creation orchestration was written out;
this module is still exclusively `ptp_service.py`'s own concern, not a
general-purpose idempotency utility other stories are meant to import.

Coordination note (unchanged from the story brief): a sibling story, E5-S4,
uses the same `idempotency_record` table in this same parallel batch for a
different purpose (AI tool-call idempotency). To avoid a same-file
collision, this module talks to `idempotency_record` through a hand-rolled
SQLAlchemy Core `Table` (never a new `persistence/orm/idempotency_record.py`
or a shared repository module) against the existing migration-0006 columns,
and is named distinctly from E5-S4's own `domain_services/idempotency.py` so
neither story's file ever collides with the other's.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Table, Text, insert, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.domain_services._ptp_exceptions import PtpConflictError
from collectai.domain_services._ptp_helpers import PtpRecordRequest, RecordPtpOutcome
from collectai.types.reason_codes import ReasonCode

_IDEMPOTENCY_SCOPE = "COLLECTIONS_OFFICER:POST:/api/ptps"
_idempotency_metadata = MetaData()
_idempotency_table = Table(
    "idempotency_record",
    _idempotency_metadata,
    Column("idempotency_id", BigInteger, primary_key=True),
    Column("scope", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("request_hash", Text, nullable=False),
    Column("response_status", Integer, nullable=False),
    Column("response_body", JSONB, nullable=False),
    Column("resource_type", Text),
    Column("resource_id", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def hash_request(request: PtpRecordRequest) -> str:
    """sha256 of the canonical (sorted-key) JSON of the fields that make up
    the request body, mirroring `config.policy.models.compute_content_hash`'s
    canonicalization so two requests differing only in key order still hash
    identically."""
    canonical = json.dumps(
        {
            "account_id": request.account_id,
            "promised_amount": request.promised_amount,
            "promised_date": request.promised_date.isoformat(),
            "interaction_reference": request.interaction_reference,
            "item_id": request.item_id,
            "record_version": request.record_version,
            "snapshot_as_of": request.snapshot_as_of.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _find(session: AsyncSession, idempotency_key: str) -> RowMapping | None:
    stmt = select(_idempotency_table).where(
        _idempotency_table.c.scope == _IDEMPOTENCY_SCOPE,
        _idempotency_table.c.idempotency_key == idempotency_key,
    )
    return (await session.execute(stmt)).mappings().one_or_none()


async def replay_if_present(
    session: AsyncSession, idempotency_key: str, request_hash: str
) -> RecordPtpOutcome | None:
    """`None` means "no stored record for this key yet, proceed". A stored
    record with a matching hash is AC4's replay; a mismatched hash is
    `IDEMPOTENCY_KEY_REUSED` (api-contracts.md 1.2)."""
    existing = await _find(session, idempotency_key)
    if existing is None:
        return None
    if existing["request_hash"] != request_hash:
        raise PtpConflictError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
            message="This Idempotency-Key was already used with a different request body.",
        )
    return RecordPtpOutcome(response_body=existing["response_body"], replayed=True)


async def insert_or_replay(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_hash: str,
    response_body: dict[str, Any],
    resource_id: str,
    created_at: datetime,
) -> RecordPtpOutcome | None:
    """Insert the idempotency record guarding this creation. On a genuine
    concurrent duplicate (unique-index violation on `(scope,
    idempotency_key)`), roll back this writer's own insert -- discarding its
    PTP row and audit event along with it -- and replay the winner's stored
    response instead (data-models.md 4.5: "the loser reads the winner's
    row"). Returns `None` when this writer's own insert won the race."""
    stmt = insert(_idempotency_table).values(
        scope=_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=201,
        response_body=response_body,
        resource_type="promise_to_pay",
        resource_id=resource_id,
        created_at=created_at,
    )
    try:
        await session.execute(stmt)
    except IntegrityError:
        await session.rollback()
        replay = await replay_if_present(session, idempotency_key, request_hash)
        if replay is not None:
            return replay
        raise PtpConflictError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED,
            message="This Idempotency-Key was already used with a different request body.",
        ) from None
    return None
