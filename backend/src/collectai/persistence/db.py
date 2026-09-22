"""Engine, session-factory construction and `UnitOfWork`.

This story builds the persistence layer other stories inject into, not a
FastAPI app itself, so it adapts the code-gen skill's "Database Session
Lifecycle" pattern: `build_engine`/`build_session_factory` are the
construction functions a composition root (`bootstrap/`) calls once, instead
of a FastAPI `lifespan`; `UnitOfWork` is the `async with ...: yield session`
equivalent for non-HTTP callers (repositories, the seed loader, the CLI).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import TracebackType

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_ASYNC_SCHEME = "postgresql+asyncpg://"
_ACCEPTED_SCHEMES: tuple[str, ...] = ("postgresql://", "postgres://", "postgresql+asyncpg://")


class UnsupportedDatabaseUrlError(ValueError):
    """Raised when `DATABASE_URL` does not use a Postgres scheme this
    application can normalize to the async driver."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"DATABASE_URL must be a postgresql:// (or postgresql+asyncpg://) URL, got: {url!r}"
        )


def normalize_database_url(database_url: str) -> str:
    """Force the asyncpg driver scheme, regardless of how the URL was written.

    Settings.database_url deliberately enforces no scheme (config/settings.py
    docstring); this is the one place that gotcha ("Sync DB driver in async
    app") is closed, for every caller of `build_engine`.
    """
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    for scheme in ("postgresql://", "postgres://"):
        if database_url.startswith(scheme):
            return _ASYNC_SCHEME + database_url[len(scheme) :]
    raise UnsupportedDatabaseUrlError(database_url)


def build_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the async engine. Callers own its lifetime and must
    `await engine.dispose()` on shutdown."""
    return create_async_engine(normalize_database_url(database_url), echo=echo, future=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory bound to `engine`. Built once per engine,
    per the code-gen skill: never construct a session manually per call."""
    return async_sessionmaker(engine, expire_on_commit=False)


class UnitOfWork:
    """One atomic session scope: commits on clean exit, rolls back on
    exception, always closes. The non-HTTP equivalent of `Depends(get_db)`.

    Usage:
        async with UnitOfWork(session_factory) as session:
            await some_repository.create(session, ...)

    E1-S4: `AuditService.record_in(session, draft)` takes this same yielded
    `AsyncSession`, not a session of its own. That is the entire mechanism
    behind "the audit event is written in the same transaction as the state
    transition it describes" (data-models.md AuditEvent) -- a business write
    and its `record_in` call inside one `UnitOfWork` block commit or roll
    back together, because they are literally the same database transaction.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self._session = self._session_factory()
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork.__aexit__ called without a matching __aenter__.")
        try:
            if exc is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """An `async with` convenience wrapper around `UnitOfWork` for callers
    that prefer a generator-style dependency (mirrors `get_db` in the
    code-gen skill's FastAPI example, adapted for non-HTTP use)."""
    async with UnitOfWork(session_factory) as session:
        yield session
