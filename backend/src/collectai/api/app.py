"""FastAPI application factory (E1-S5, extended by E3-S1). Wires the RBAC
error envelope, correlation-id middleware and every router. CORS is left to
a later story (folder-structure.md's `deploy/nginx` terminates the public
edge in the demo compose stack; no story in this group needs cross-origin
API access yet).

Session lifecycle follows `.claude/skills/code-gen/SKILL.md`'s FastAPI
pattern: the engine and session factory are built once in `lifespan` and
stored on `app.state`, disposed on shutdown; each request gets its own
session via `Depends(get_db)`, never a manually constructed one. E3-S1
extends the same `lifespan` to also build the `Clock` and `AuditService`
every non-public route's `require_capability` dependency needs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from collectai.api.middleware.errors import correlation_id_middleware, register_error_handlers
from collectai.api.routers.session import router as session_router
from collectai.api.routers.system import router as system_router
from collectai.audit.service import AuditService
from collectai.config.settings import Settings
from collectai.persistence.db import build_engine, build_session_factory
from collectai.types.clock import Clock, SystemClock


def create_app(settings: Settings, *, clock: Clock | None = None) -> FastAPI:
    """Build the ASGI application for `settings`. Callers own the returned
    app's lifespan (uvicorn drives it in production; tests drive it via
    `TestClient` as a context manager). `clock` defaults to `SystemClock()`;
    tests inject a `SimulatedClock` for deterministic audit timestamps."""
    active_clock = clock if clock is not None else SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        app.state.session_factory = session_factory
        app.state.clock = active_clock
        app.state.audit_service = AuditService(active_clock, session_factory)
        yield
        await engine.dispose()

    app = FastAPI(title="CollectAI API", lifespan=lifespan)
    app.middleware("http")(correlation_id_middleware)
    register_error_handlers(app)
    app.include_router(system_router)
    app.include_router(session_router)
    return app
