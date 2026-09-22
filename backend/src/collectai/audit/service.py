"""`AuditService`: append-only, transactional audit writes (E1-S4).

`record_in(session, draft)` writes inside the caller's existing transaction
(AC1, AC3): a flush failure propagates to the caller, whose own
`UnitOfWork.__aexit__` rolls back, so no state transition ever persists
without its audit event. `record(draft)` is for non-state-changing AI
activity: it opens its own transaction and raises `AuditUnavailable` on
failure so callers cannot report the activity as audited (AC5).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from collectai.audit.events import AuditEventDraft
from collectai.audit.redaction import redact_value
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.types.clock import Clock
from collectai.types.ids import EntityPrefix, generate_id

logger = logging.getLogger(__name__)


class AuditUnavailable(Exception):
    """Raised by `AuditService.record` when a non-state-changing audit
    event could not be persisted (AC5). Callers must not report the
    described activity as audited."""

    def __init__(self, *, event_type: str, correlation_id: str) -> None:
        self.event_type = event_type
        self.correlation_id = correlation_id
        super().__init__(
            f"Audit event {event_type!r} (correlation_id={correlation_id!r}) "
            "could not be persisted."
        )


class AuditService:
    """Builds and persists `AuditEventDraft`s as append-only `audit_event`
    rows, with redaction applied before every write."""

    def __init__(
        self,
        clock: Clock,
        session_factory: async_sessionmaker[AsyncSession],
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock
        self._session_factory = session_factory
        self._id_factory = id_factory or (lambda: generate_id(EntityPrefix.AUDIT_EVENT))

    async def record_in(self, session: AsyncSession, draft: AuditEventDraft) -> None:
        """Insert inside the caller's existing transaction (AC1, AC3)."""
        orm = self._draft_to_orm(draft)
        session.add(orm)
        await session.flush()

    async def record(self, draft: AuditEventDraft) -> None:
        """Insert in its own transaction, for non-state-changing AI
        activity. Raises `AuditUnavailable` on failure (AC5) and logs an
        operational failure line with no customer data."""
        orm = self._draft_to_orm(draft)
        try:
            async with self._session_factory() as session:
                session.add(orm)
                await session.commit()
        except SQLAlchemyError as exc:
            logger.error(
                "Audit persistence failed for non-state-changing activity",
                extra={
                    "event_type": draft.event_type,
                    "correlation_id": draft.correlation_id,
                    "capability": draft.capability,
                },
            )
            raise AuditUnavailable(
                event_type=draft.event_type, correlation_id=draft.correlation_id
            ) from exc

    def _draft_to_orm(self, draft: AuditEventDraft) -> AuditEventOrm:
        redacted_fields = redact_value(draft.model_dump(mode="json"))
        assert isinstance(redacted_fields, dict)  # noqa: S101 - draft.model_dump() is always a dict
        return AuditEventOrm(
            audit_event_id=self._id_factory(),
            timestamp=self._clock.now(),
            **redacted_fields,
        )
