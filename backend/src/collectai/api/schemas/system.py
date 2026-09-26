"""Wire models for the system endpoints (api-contracts.schema.json
HealthStatus, ReadyCheck, ReadyStatus)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthStatus(BaseModel):
    """Liveness. `status` is always "ok" when the process is up."""

    model_config = ConfigDict(frozen=True)

    status: str


class ReadyCheck(BaseModel):
    """One readiness check (database, migrations, policy_ruleset,
    audit_role_grants, app_role_grants)."""

    model_config = ConfigDict(frozen=True)

    name: str
    ok: bool
    detail: str | None


class ReadyStatus(BaseModel):
    """Readiness. `status` is "ready" or "not_ready"; the 503 response uses
    this same shape, per api-contracts.md ("503 SERVICE_UNAVAILABLE:
    not_ready, body still ReadyStatus")."""

    model_config = ConfigDict(frozen=True)

    status: str
    checks: list[ReadyCheck]
