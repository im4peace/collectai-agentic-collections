"""Generic, reusable idempotency service (E5-S4; data-models.md section 4.5,
`IdempotencyRecord`).

Backs PROPOSE-tool idempotency (this story, AC3) and is intentionally
generic enough for a future API-level idempotent-endpoint mechanism too --
though those two kinds of caller derive `key` very differently
(deterministic from `(turn_id, tool_name, canonical arguments)` vs. a
client-supplied header). This module only ever sees an already-decided
`key`; it never derives one itself.

Insert-or-fetch-existing, not check-then-insert: a pre-check `SELECT` is
still used as a fast path (so the common, purely-sequential replay case in
this demo never re-runs `compute_response`'s rules-engine check), but the
actual insert is wrapped in a `SAVEPOINT` (`session.begin_nested()`) with a
real DB-level `IntegrityError` handler as the correctness guarantee for a
genuine concurrent race -- the pre-check alone is never trusted to be
race-free.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.idempotency_record import IdempotencyRecordOrm
from collectai.persistence.repositories.idempotency_repository import IdempotencyRepository
from collectai.types.clock import Clock

# `response_status` mirrors a column this table shares with a *different*
# (API-level, HTTP) idempotency mechanism, where it holds a real HTTP status.
# A PROPOSE-tool call has no HTTP response of its own -- by the time this
# service runs, dispatch has already rejected any schema-invalid call, so
# every row a tool call writes here is a "successful" typed result -- so this
# service always writes the fixed constant 200, purely to satisfy the shared
# NOT NULL column; no caller of `get_or_create` ever branches on it.
_FIXED_RESPONSE_STATUS = 200


class IdempotencyService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def get_or_create(
        self,
        session: AsyncSession,
        *,
        scope: str,
        key: str,
        request_hash: str,
        resource_type: str | None,
        resource_id: str | None,
        compute_response: Callable[[], Awaitable[dict[str, object]]],
    ) -> tuple[dict[str, object], bool]:
        """Return `(response_body, was_replayed)`.

        On replay (an existing `(scope, key)` row, whether found by the
        fast-path pre-check or by the conflict-handler re-select below),
        returns the stored `response_body` unchanged -- `compute_response`
        is never re-invoked once a row is known to exist.
        """
        repository = IdempotencyRepository()
        existing = await repository.get_by_scope_and_key(session, scope, key)
        if existing is not None:
            return existing.response_body, True

        response_body = await compute_response()
        entity = IdempotencyRecordOrm(
            scope=scope,
            idempotency_key=key,
            request_hash=request_hash,
            response_status=_FIXED_RESPONSE_STATUS,
            response_body=response_body,
            resource_type=resource_type,
            resource_id=resource_id,
            created_at=self._clock.now(),
        )
        try:
            async with session.begin_nested():
                await repository.create(session, entity)
        except IntegrityError:
            winner = await repository.get_by_scope_and_key(session, scope, key)
            if winner is None:
                raise
            return winner.response_body, True
        return response_body, False
