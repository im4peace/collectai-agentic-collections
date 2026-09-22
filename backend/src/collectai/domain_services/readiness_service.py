"""Readiness checks backing `GET /api/ready` (E1-S5 AC1, AC2).

Lives in `domain_services` (layer 5a), not `api` (layer 7), because the
layering table in `specs/design/folder-structure.md` section 5 does not let
`api` import `persistence` directly — only `application`, `domain_services`,
`audit`, `types`, `config`. `api/routers/system.py` calls `check_readiness`
and maps the result to HTTP; this module owns the actual DB introspection.

Check names match the `ReadyCheck.name` values named in
`specs/design/api-contracts.schema.json` ("database, migrations,
policy_ruleset, audit_role_grants").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "persistence" / "migrations"
_REQUIRED_AUDIT_APP_PRIVILEGES = frozenset({"INSERT", "SELECT"})


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One named readiness check result. `detail` is always safe to expose
    (no connection strings, no stack traces, no customer data)."""

    name: str
    ok: bool
    detail: str | None


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    """The full readiness verdict: ready only when every check passed."""

    ready: bool
    checks: tuple[ReadinessCheck, ...]


async def check_readiness(session: AsyncSession) -> ReadinessResult:
    """Run every readiness check against `session` and combine the results.

    Each `_check_*` function is defensive: a failure in one check must never
    raise out of this function and must never leave `session` unusable for
    the checks that run after it.
    """
    checks = (
        await _check_database(session),
        await _check_migrations(session),
        await _check_policy_ruleset(session),
        await _check_audit_role_grants(session),
    )
    return ReadinessResult(ready=all(check.ok for check in checks), checks=checks)


async def _check_database(session: AsyncSession) -> ReadinessCheck:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        await _safe_rollback(session)
        return ReadinessCheck(name="database", ok=False, detail="database unreachable")
    return ReadinessCheck(name="database", ok=True, detail=None)


async def _check_migrations(session: AsyncSession) -> ReadinessCheck:
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
    except SQLAlchemyError:
        await _safe_rollback(session)
        return ReadinessCheck(name="migrations", ok=False, detail="migrations not applied")
    if row is None:
        return ReadinessCheck(name="migrations", ok=False, detail="migrations not applied")
    current_revision = row[0]
    head_revision = _head_revision()
    if current_revision != head_revision:
        return ReadinessCheck(
            name="migrations",
            ok=False,
            detail=f"database is at {current_revision!r}, expected head {head_revision!r}",
        )
    return ReadinessCheck(name="migrations", ok=True, detail=None)


def _head_revision() -> str | None:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("path_separator", "os")
    return ScriptDirectory.from_config(config).get_current_head()


async def _check_policy_ruleset(session: AsyncSession) -> ReadinessCheck:
    try:
        result = await session.execute(
            text("SELECT count(*) FROM policy_rule_set WHERE is_active")
        )
        active_count = result.scalar_one()
    except SQLAlchemyError:
        await _safe_rollback(session)
        return ReadinessCheck(
            name="policy_ruleset", ok=False, detail="policy_rule_set not migrated"
        )
    if active_count != 1:
        return ReadinessCheck(
            name="policy_ruleset",
            ok=False,
            detail=f"expected exactly one active policy version, found {active_count}",
        )
    return ReadinessCheck(name="policy_ruleset", ok=True, detail=None)


async def _check_audit_role_grants(session: AsyncSession) -> ReadinessCheck:
    try:
        result = await session.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'collectai_app' AND table_name = 'audit_event'"
            )
        )
        granted = {row[0] for row in result}
    except SQLAlchemyError:
        await _safe_rollback(session)
        return ReadinessCheck(
            name="audit_role_grants", ok=False, detail="audit_event not migrated"
        )
    if not granted:
        return ReadinessCheck(
            name="audit_role_grants", ok=False, detail="no grants found for collectai_app"
        )
    if granted != _REQUIRED_AUDIT_APP_PRIVILEGES:
        return ReadinessCheck(
            name="audit_role_grants",
            ok=False,
            detail=f"expected exactly {sorted(_REQUIRED_AUDIT_APP_PRIVILEGES)}, "
            f"found {sorted(granted)}",
        )
    return ReadinessCheck(name="audit_role_grants", ok=True, detail=None)


async def _safe_rollback(session: AsyncSession) -> None:
    """Recover the session from an aborted transaction so later checks in
    the same `check_readiness` call (or a caller's own subsequent query)
    are not left unusable."""
    try:
        await session.rollback()
    except SQLAlchemyError:
        pass
