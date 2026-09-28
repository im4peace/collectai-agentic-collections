"""`deploy/db/init-roles.sql` applies cleanly against the migrated schema and
grants the three roles the access `data-models.md` section 1 describes.

Not tied to a specific acceptance criterion (init-roles.sql is a deployment
deliverable owned by this story per component-map.md, not directly exercised
by any of the 7 ACs), but it is a required file and this proves it is valid,
idempotent SQL against the real schema rather than an unverified artifact.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.db

_INIT_ROLES_SQL_PATH = (
    Path(__file__).resolve().parents[3] / "deploy" / "db" / "init-roles.sql"
)


def _sync_dsn(async_database_url: str) -> str:
    return async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def test_init_roles_sql_file_exists() -> None:
    assert _INIT_ROLES_SQL_PATH.is_file()


def test_init_roles_sql_applies_cleanly_to_the_migrated_schema(migrated_schema: str) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)


def test_init_roles_sql_is_idempotent_when_run_twice(migrated_schema: str) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        conn.execute(sql)


def test_all_three_roles_exist_after_applying(migrated_schema: str) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname IN ('collectai_owner', 'collectai_app', 'collectai_readonly') "
            "ORDER BY rolname"
        ).fetchall()
    assert [row[0] for row in rows] == [
        "collectai_app",
        "collectai_owner",
        "collectai_readonly",
    ]


def test_collectai_app_can_insert_and_select_but_not_update_payment_event(
    migrated_schema: str,
) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_app' AND table_name = 'payment_event' "
            "ORDER BY privilege_type"
        ).fetchall()
    granted = {row[0] for row in rows}
    assert granted == {"INSERT", "SELECT"}
    assert "UPDATE" not in granted


def test_collectai_app_can_select_but_not_write_alembic_version(migrated_schema: str) -> None:
    """The application connects as `collectai_app` (deployment.md: "the running app never holds
    owner rights") and the readiness check `migrations` reads `alembic_version` on that same
    connection. Without this grant, PostgreSQL's default "no privilege" for a non-owner role
    made that SELECT fail with a permission error, which the check reported as "migrations not
    applied" even though migrations had run (CI evidence: db/policy_ruleset/audit_role_grants/
    app_role_grants all ok, only migrations failed). collectai_app never writes this table --
    only collectai_owner does, via Alembic -- so SELECT is the only grant."""
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_app' AND table_name = 'alembic_version'"
        ).fetchall()
    assert {row[0] for row in rows} == {"SELECT"}


def test_collectai_readonly_has_no_grant_on_alembic_version(migrated_schema: str) -> None:
    """Migration state is not a reporting/evaluation concern; only `collectai_app` needs it,
    to answer its own readiness check."""
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_readonly' AND table_name = 'alembic_version'"
        ).fetchall()
    assert rows == []


def test_collectai_readonly_has_select_only_on_account(migrated_schema: str) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_readonly' AND table_name = 'account'"
        ).fetchall()
    assert {row[0] for row in rows} == {"SELECT"}


def test_init_roles_sql_grants_no_privileges_on_audit_event(migrated_schema: str) -> None:
    """`init-roles.sql` deliberately never mentions `audit_event` (E1-S4's
    migration 0007 owns that table's own append-only grants, per the
    comment in init-roles.sql). Confirm applying this file grants nothing
    extra on top of what 0007 already granted."""
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        before = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_app' AND table_name = 'audit_event'"
        ).fetchall()
        conn.execute(sql)
        after = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_app' AND table_name = 'audit_event'"
        ).fetchall()
    assert {row[0] for row in before} == {row[0] for row in after}


def test_collectai_app_can_insert_and_select_but_not_update_delete_audit_event(
    migrated_schema: str,
) -> None:
    """E1-S4 AC2: the application role has INSERT and SELECT only on
    `audit_event`. Migration 0007 grants this itself, guarded by a
    role-existence check (see `_ddl_helpers.guarded_insert_select_grant_sql`)
    because `migrated_schema` applies migrations before this file's
    `init-roles.sql` creates the role -- so this test re-runs that exact
    guarded grant statement after creating the role, reproducing the real
    deployment order (role exists before migrations run; deployment.md
    section 2) without duplicating the SQL by hand."""
    from collectai.persistence.migrations._ddl_helpers import (
        guarded_insert_select_grant_sql,
    )

    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        conn.execute(guarded_insert_select_grant_sql("audit_event"))
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_app' AND table_name = 'audit_event' "
            "ORDER BY privilege_type"
        ).fetchall()
    granted = {row[0] for row in rows}
    assert granted == {"INSERT", "SELECT"}
