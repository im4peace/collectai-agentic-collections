"""Readiness checks backing `GET /api/ready` (E1-S5 AC1, AC2).

Lives in `domain_services` (layer 5a), not `api` (layer 7), because the
layering table in `specs/design/folder-structure.md` section 5 does not let
`api` import `persistence` directly — only `application`, `domain_services`,
`audit`, `types`, `config`. `api/routers/system.py` calls `check_readiness`
and maps the result to HTTP; this module owns the actual DB introspection.

Check names match the `ReadyCheck.name` values named in
`specs/design/api-contracts.schema.json` ("database, migrations,
policy_ruleset, audit_role_grants, app_role_grants").
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

_APP_ROLE = "collectai_app"
# Tables the application role may only INSERT into and SELECT from (no UPDATE, no DELETE):
# `deploy/db/init-roles.sql`'s insert-only list plus `audit_event`, whose grants migration 0007
# owns. A test ties this set to that file. Every other public table also needs UPDATE.
_INSERT_ONLY_TABLES = frozenset({"audit_event", "chat_message", "payment_event", "review_decision"})
_MAX_TABLES_LISTED = 5


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
        await _check_app_role_grants(session),
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
        active_count: int = result.scalar_one()
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


def _table_list(tables: list[str]) -> str:
    shown = ", ".join(tables[:_MAX_TABLES_LISTED])
    extra = len(tables) - _MAX_TABLES_LISTED
    return f"{shown} (+{extra} more)" if extra > 0 else shown


async def _check_app_role_grants(session: AsyncSession) -> ReadinessCheck:
    """The application role's real privileges on the actual public tables.

    `audit_role_grants` only looks at `audit_event`, so it could pass while the role cannot read
    any other table (the state Docker was left in when the table grants ran before the tables
    existed). This verifies every public application table (everything but `alembic_version`):
    SELECT and INSERT everywhere, UPDATE on every table except the insert-only ones, and no
    DELETE anywhere, and no UPDATE on the insert-only tables (intentional least privilege). It
    reads privileges with `has_table_privilege`, so it reports what the role can really do, not
    what a grant list says. It never raises and lists at most a few table names.
    """
    name = "app_role_grants"
    try:
        role = await session.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": _APP_ROLE}
        )
        if role.first() is None:
            return ReadinessCheck(name=name, ok=False, detail=f"role {_APP_ROLE} does not exist")
        # `_APP_ROLE` is a module constant, never input: inlined because an untyped bind
        # parameter makes has_table_privilege's overload ambiguous.
        privileges = "".join(
            f", has_table_privilege('{_APP_ROLE}', format('%I.%I', schemaname, tablename), '{p}')"
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
        )
        result = await session.execute(
            text(
                f"SELECT tablename{privileges} FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
                "ORDER BY tablename"
            )
        )
        rows = result.all()
    except SQLAlchemyError:
        await _safe_rollback(session)
        return ReadinessCheck(name=name, ok=False, detail="could not read table privileges")
    if not rows:
        return ReadinessCheck(name=name, ok=False, detail="no application tables found")

    missing: list[str] = []
    forbidden: list[str] = []
    for table, can_select, can_insert, can_update, can_delete in rows:
        insert_only = table in _INSERT_ONLY_TABLES
        if not (can_select and can_insert and (can_update or insert_only)):
            missing.append(table)
        if can_delete or (insert_only and can_update):
            forbidden.append(table)
    if missing:
        return ReadinessCheck(
            name=name,
            ok=False,
            detail=f"{_APP_ROLE} lacks required privileges on: {_table_list(missing)}",
        )
    if forbidden:
        return ReadinessCheck(
            name=name,
            ok=False,
            detail=f"{_APP_ROLE} holds forbidden UPDATE/DELETE on: {_table_list(forbidden)}",
        )
    return ReadinessCheck(name=name, ok=True, detail=None)


async def _safe_rollback(session: AsyncSession) -> None:
    """Recover the session from an aborted transaction so later checks in
    the same `check_readiness` call (or a caller's own subsequent query)
    are not left unusable."""
    try:
        await session.rollback()
    except SQLAlchemyError:
        pass
