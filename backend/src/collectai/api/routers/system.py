"""System endpoints (api-contracts.md 3.1): `GET /api/health`, `GET /api/ready`.
Both are `x-capability: public` — no persona resolution, no auth (that
layer does not exist until E3-S1)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from collectai.api.deps import DbSession
from collectai.api.schemas.system import HealthStatus, ReadyCheck, ReadyStatus
from collectai.domain_services.readiness_service import ReadinessResult, check_readiness

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health", response_model=HealthStatus)
async def get_health() -> HealthStatus:
    """Liveness probe: always 200 while the process is up. No DB access."""
    return HealthStatus(status="ok")


@router.get("/ready")
async def get_ready(session: DbSession) -> JSONResponse:
    """Readiness: database, migrations, active PolicyRuleSet, audit role
    grants. Returns 503 with the same `ReadyStatus` body when not ready
    (api-contracts.md: "503 SERVICE_UNAVAILABLE: not_ready, body still
    ReadyStatus"), not the generic error envelope."""
    result = await check_readiness(session)
    body = _to_ready_status(result)
    status_code = 200 if result.ready else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _to_ready_status(result: ReadinessResult) -> ReadyStatus:
    return ReadyStatus(
        status="ready" if result.ready else "not_ready",
        checks=[ReadyCheck(name=c.name, ok=c.ok, detail=c.detail) for c in result.checks],
    )
