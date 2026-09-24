"""Private `Idempotency-Key` storage for `POST .../recommendation/{id}/decision`
(E4-S3; api-contracts.md 3.5).

Mirrors `domain_services._ptp_idempotency.py`'s pattern exactly, including
its reason for existing: this endpoint's own scope talks to the shared
`idempotency_record` table (migration 0006) through a hand-rolled SQLAlchemy
Core `Table`, never a new ORM class or the generic
`domain_services.idempotency.IdempotencyService` (which replays on key match
alone and never raises on a request-hash mismatch -- this endpoint needs the
409 `IDEMPOTENCY_KEY_REUSED` conflict api-contracts.md documents for "same
key, different body"). A dedicated module and scope constant keeps this
story's use of the shared table from ever colliding with any other story's.
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

from collectai.types.reason_codes import ReasonCode

_IDEMPOTENCY_SCOPE = "COLLECTIONS_OFFICER:POST:/api/accounts/*/recommendation/*/decision"
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


class RecommendationDecisionIdempotencyConflict(Exception):
    """The `Idempotency-Key` was already used with a different request body
    (409 `IDEMPOTENCY_KEY_REUSED`)."""

    def __init__(self) -> None:
        super().__init__("This Idempotency-Key was already used with a different request body.")
        self.reason_code = ReasonCode.IDEMPOTENCY_KEY_REUSED


def hash_decision_request(
    *, recommendation_id: str, decision: str, reason: str | None, chosen_action: str | None
) -> str:
    canonical = json.dumps(
        {
            "recommendation_id": recommendation_id,
            "decision": decision,
            "reason": reason,
            "chosen_action": chosen_action,
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
) -> dict[str, Any] | None:
    """`None` means "no stored record for this key yet, proceed". A stored
    record with a matching hash is a replay (the caller returns its
    `response_body` unchanged); a mismatched hash is
    `RecommendationDecisionIdempotencyConflict`."""
    existing = await _find(session, idempotency_key)
    if existing is None:
        return None
    if existing["request_hash"] != request_hash:
        raise RecommendationDecisionIdempotencyConflict()
    return dict(existing["response_body"])


async def insert_or_replay(
    session: AsyncSession,
    *,
    idempotency_key: str,
    request_hash: str,
    response_body: dict[str, Any],
    resource_id: str,
    created_at: datetime,
) -> dict[str, Any] | None:
    """Insert the idempotency record guarding this decision. On a genuine
    concurrent duplicate (unique-index violation on `(scope,
    idempotency_key)`), roll back this writer's own insert and replay the
    winner's stored response instead. Returns `None` when this writer's own
    insert won the race."""
    stmt = insert(_idempotency_table).values(
        scope=_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_status=200,
        response_body=response_body,
        resource_type="recommendation",
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
        raise RecommendationDecisionIdempotencyConflict() from None
    return None


__all__ = [
    "RecommendationDecisionIdempotencyConflict",
    "hash_decision_request",
    "insert_or_replay",
    "replay_if_present",
]
