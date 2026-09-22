"""FastAPI application factory (E1-S5). Deliberately narrow: only the
system router (`/api/health`, `/api/ready`) is wired here. Later stories
(starting with E3-S1) extend this factory with RBAC, CORS, correlation-id
and error-envelope middleware and further routers — see
`specs/design/component-map.md`'s E3-S1 row ("modifies `be/api/app.py`").

Session lifecycle follows `.claude/skills/code-gen/SKILL.md`'s FastAPI
pattern: the engine and session factory are built once in `lifespan` and
stored on `app.state`, disposed on shutdown; each request gets its own
session via `Depends(get_db)`, never a manually constructed one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from collectai.api.routers.system import router as system_router
from collectai.config.settings import Settings
from collectai.persistence.db import build_engine, build_session_factory


def create_app(settings: Settings) -> FastAPI:
    """Build the ASGI application for `settings`. Callers own the returned
    app's lifespan (uvicorn drives it in production; tests drive it via
    `TestClient` as a context manager)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        app.state.session_factory = build_session_factory(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="CollectAI API", lifespan=lifespan)
    app.include_router(system_router)
    return app
