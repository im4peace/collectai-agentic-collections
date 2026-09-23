"""E3-S1 AC1-AC5: server-side persona RBAC.

A synthetic probe router -- one route per capability in
`rbac.CAPABILITY_MATRIX` -- is mounted onto the real app for this test only.
This proves the *enforcement mechanism* end to end for the full capability
matrix now, even though most of the business routes that will eventually
declare these capabilities are built by later stories (Groups E-I); the
"generated role x endpoint matrix test" (AC3) then walks every route
actually registered on the app -- `/api/health`, `/api/ready`, the real
session endpoints, and the probe routes -- exactly as it will keep doing
once real routes replace some of the probes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.deps import PersonaContext, require_capability
from collectai.api.rbac import CAPABILITY_MATRIX, PUBLIC_CAPABILITY, is_capability_allowed
from collectai.audit import queries
from collectai.types.enums import Persona

pytestmark = pytest.mark.db

# Capabilities api-contracts.md 1.7 documents as mutating (POST/PUT/PATCH/
# DELETE in the real API); the probe for each is a POST so AC4/AC5's
# "every mutating endpoint" claim is exercised, not just the read ones.
_MUTATING_CAPABILITIES = frozenset(
    {
        "chat:use",
        "compliance:decide",
        "demo_controls:use",
        "dispute:resolve",
        "escalation:review",
        "ptp:record",
        "recommendation:decide",
        "recommendation:generate",
        "self:write",
    }
)


def _register_probe_route(router: APIRouter, capability: str, *, mutating: bool) -> None:
    path = f"/{capability.replace(':', '-')}"

    require_this_capability = require_capability(capability)

    async def _handler(
        persona_context: PersonaContext = Depends(require_this_capability),  # noqa: B008
    ) -> dict[str, str]:
        return {"persona": persona_context.persona.value}

    register = router.post if mutating else router.get
    register(path, openapi_extra={"x-capability": capability})(_handler)


def _build_probe_router() -> APIRouter:
    router = APIRouter(prefix="/api/_probe")
    for capability in sorted(CAPABILITY_MATRIX):
        _register_probe_route(router, capability, mutating=capability in _MUTATING_CAPABILITIES)
    return router


@pytest.fixture
def probe_client(api_client: TestClient) -> Iterator[TestClient]:
    api_client.app.include_router(_build_probe_router())
    yield api_client


def _iter_api_routes(routes: Iterable[object]) -> Iterator[APIRoute]:
    """Recursively find every `APIRoute`. Newer FastAPI/Starlette versions
    wrap an `include_router`-ed router in an opaque container (exposing the
    original `APIRouter` as `.original_router`) instead of flattening its
    routes into the parent's `.routes` list, so a plain `isinstance` filter
    over `app.routes` alone misses everything under a router -- which, on
    this app, is every route this test needs to see."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        nested_router = getattr(route, "original_router", None)
        if nested_router is not None:
            yield from _iter_api_routes(nested_router.routes)


def _registered_routes(app: FastAPI) -> list[tuple[str, str, str]]:
    """`(method, path, capability)` for every route with an HTTP method.
    An undeclared `x-capability` (E1-S5's `/api/health`, `/api/ready`) is
    public by contract (api-contracts.md 3.1)."""
    routes: list[tuple[str, str, str]] = []
    for route in _iter_api_routes(app.routes):
        extra = route.openapi_extra or {}
        capability = extra.get("x-capability", PUBLIC_CAPABILITY)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            routes.append((method, route.path, capability))
    return routes


def _headers_for(persona: Persona, customer_session_headers: dict[str, str]) -> dict[str, str]:
    if persona is Persona.CUSTOMER:
        return customer_session_headers
    return {"X-Persona": persona.value}


def test_every_registered_capability_is_public_or_a_known_matrix_entry(
    probe_client: TestClient,
) -> None:
    for _, _, capability in _registered_routes(probe_client.app):
        assert capability == PUBLIC_CAPABILITY or capability in CAPABILITY_MATRIX


def test_public_routes_never_401_or_403_regardless_of_persona(probe_client: TestClient) -> None:
    public_routes = [
        (method, path)
        for method, path, capability in _registered_routes(probe_client.app)
        if capability == PUBLIC_CAPABILITY
    ]
    assert public_routes, "expected at least one public route (system + session/options)"
    for method, path in public_routes:
        for headers in ({}, {"X-Persona": "COLLECTIONS_OFFICER"}, {"X-Persona": "not-a-persona"}):
            response = probe_client.request(method, path, headers=headers)
            assert response.status_code not in (401, 403), (method, path, headers)


def test_missing_persona_header_returns_401_on_every_non_public_route(
    probe_client: TestClient,
) -> None:
    for method, path, capability in _registered_routes(probe_client.app):
        if capability == PUBLIC_CAPABILITY:
            continue
        response = probe_client.request(method, path)
        assert response.status_code == 401, (method, path)
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("persona", list(Persona))
def test_matrix_allow_deny_outcome_for_every_registered_route(
    probe_client: TestClient,
    persona: Persona,
    customer_session_headers: dict[str, str],
) -> None:
    """AC1, AC3: the documented allow/deny outcome, for every route and
    every persona."""
    for method, path, capability in _registered_routes(probe_client.app):
        if capability == PUBLIC_CAPABILITY:
            continue
        headers = _headers_for(persona, customer_session_headers)
        response = probe_client.request(method, path, headers=headers)
        if is_capability_allowed(capability, persona):
            assert response.status_code not in (401, 403), (method, path, persona)
        else:
            assert response.status_code == 403, (method, path, persona)
            assert response.json()["error"]["code"] == "FORBIDDEN"


def test_collections_manager_is_forbidden_on_every_mutating_probe_route(
    probe_client: TestClient,
) -> None:
    """AC4."""
    for method, path, capability in _registered_routes(probe_client.app):
        if capability not in _MUTATING_CAPABILITIES:
            continue
        response = probe_client.request(
            method, path, headers={"X-Persona": Persona.COLLECTIONS_MANAGER.value}
        )
        assert response.status_code == 403, (method, path)


def test_compliance_risk_is_forbidden_on_every_mutating_probe_route_except_compliance_decide(
    probe_client: TestClient,
) -> None:
    """AC5: COMPLIANCE_RISK holds no mutating capability besides
    `compliance:decide`."""
    headers = {"X-Persona": Persona.COMPLIANCE_RISK.value}
    for method, path, capability in _registered_routes(probe_client.app):
        if capability not in _MUTATING_CAPABILITIES or capability == "compliance:decide":
            continue
        response = probe_client.request(method, path, headers=headers)
        assert response.status_code == 403, (method, path)

    allowed = probe_client.post("/api/_probe/compliance-decide", headers=headers)
    assert allowed.status_code != 403


@pytest.mark.asyncio
async def test_a_403_writes_an_access_denied_audit_event_with_persona_and_endpoint(
    probe_client: TestClient, session: AsyncSession
) -> None:
    """AC2. COLLECTIONS_OFFICER (a staff persona, so a bare `X-Persona`
    header is enough to authenticate) does not hold `audit:read`."""
    response = probe_client.get(
        "/api/_probe/audit-read", headers={"X-Persona": Persona.COLLECTIONS_OFFICER.value}
    )
    assert response.status_code == 403
    correlation_id = response.headers["X-Correlation-Id"]

    events = await queries.list_by_correlation_id(session, correlation_id)

    denial_events = [event for event in events if event.event_type == "ACCESS_DENIED"]
    assert len(denial_events) == 1
    event = denial_events[0]
    assert event.actor_persona is Persona.COLLECTIONS_OFFICER
    assert event.capability == "audit:read"
    assert event.final_action is not None and "/api/_probe/audit-read" in event.final_action
    assert event.correlation_id == correlation_id
