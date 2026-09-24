"""FastAPI application factory (E1-S5, extended by E3-S1, Group E and
Group F). Wires the RBAC error envelope, correlation-id middleware and
every router. CORS is left to a later story (folder-structure.md's
`deploy/nginx` terminates the public edge in the demo compose stack; no
story in this group needs cross-origin API access yet).

Session lifecycle follows `.claude/skills/code-gen/SKILL.md`'s FastAPI
pattern: the engine and session factory are built once in `lifespan` and
stored on `app.state`, disposed on shutdown; each request gets its own
session via `Depends(get_db)`, never a manually constructed one. E3-S1
extends the same `lifespan` to also build the `Clock` and `AuditService`
every non-public route's `require_capability` dependency needs.

Group E integration pass: every Group E router (`audit`, `customer360`,
`me`, `portfolio`, `ptps`) is wired in here now that all six of that
group's stories have landed, per the "the orchestrator wires every sibling
router in once every Group E story lands" note each of those routers'
own docstrings left for this pass. `lifespan` now also builds and activates
the seed `PolicyProvider` `api/deps.py`'s `PolicyProviderDep` (and each of
those routers' own same-shaped local fallback) expects on `app.state` --
mirroring the exact seed load `bootstrap.main.run_startup_validation`
already performs, so this and real startup never disagree about which
policy is active.

Group F integration pass: `chat` (E6-S1) and `recommendations` (E4-S3) are
wired in the same way, and `lifespan` now also builds the real `LlmProvider`
from `settings.llm_mode` and stores it (plus `settings` itself and the
resolved `ProviderMode`) on `app.state`, so `recommendations.py`'s
`get_llm_provider`/`get_provider_mode` and `chat.py`'s `get_settings`
resolve to the real, configured provider instead of their MOCK-mode
fallbacks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from collectai.api.middleware.errors import correlation_id_middleware, register_error_handlers
from collectai.api.routers.audit import router as audit_router
from collectai.api.routers.chat import router as chat_router
from collectai.api.routers.customer360 import router as customer360_router
from collectai.api.routers.me import router as me_router
from collectai.api.routers.portfolio import router as portfolio_router
from collectai.api.routers.ptps import router as ptps_router
from collectai.api.routers.recommendations import router as recommendations_router
from collectai.api.routers.session import router as session_router
from collectai.api.routers.system import router as system_router
from collectai.audit.service import AuditService
from collectai.config.policy.loader import SEED_POLICY_V1_VERSION, load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import Settings
from collectai.llm_provider.factory import get_provider
from collectai.persistence.db import build_engine, build_session_factory
from collectai.types.clock import Clock, SystemClock
from collectai.types.enums import ProviderMode


def _build_default_policy_provider(clock: Clock) -> PolicyProvider:
    """The seed `policy-v1` `PolicyProvider`, registered and activated the
    same way `bootstrap.main.run_startup_validation` does at real startup.
    `create_app` builds one by default so every Group E router's
    `PolicyProviderDep` resolves to a real active policy without every
    caller (including test `conftest.py` fixtures) having to build one by
    hand; `build_app` below passes the already-validated one from startup
    instead of paying to load the seed file twice."""
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate(SEED_POLICY_V1_VERSION, clock)
    return provider


def create_app(
    settings: Settings, *, clock: Clock | None = None, policy_provider: PolicyProvider | None = None
) -> FastAPI:
    """Build the ASGI application for `settings`. Callers own the returned
    app's lifespan (uvicorn drives it in production; tests drive it via
    `TestClient` as a context manager). `clock` defaults to `SystemClock()`;
    tests inject a `SimulatedClock` for deterministic audit timestamps.
    `policy_provider` defaults to a freshly activated seed `policy-v1`."""
    active_clock = clock if clock is not None else SystemClock()
    active_policy_provider = (
        policy_provider
        if policy_provider is not None
        else _build_default_policy_provider(active_clock)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)
        app.state.session_factory = session_factory
        app.state.clock = active_clock
        app.state.audit_service = AuditService(active_clock, session_factory)
        app.state.policy_provider = active_policy_provider
        app.state.settings = settings
        app.state.llm_provider = get_provider(settings)
        app.state.llm_provider_mode = ProviderMode(settings.llm_mode.value)
        yield
        await engine.dispose()

    app = FastAPI(title="CollectAI API", lifespan=lifespan)
    app.middleware("http")(correlation_id_middleware)
    register_error_handlers(app)
    app.include_router(system_router)
    app.include_router(session_router)
    app.include_router(audit_router)
    app.include_router(customer360_router)
    app.include_router(me_router)
    app.include_router(portfolio_router)
    app.include_router(ptps_router)
    app.include_router(chat_router)
    app.include_router(recommendations_router)
    return app
