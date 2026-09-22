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


def test_collectai_readonly_has_select_only_on_account(migrated_schema: str) -> None:
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        rows = conn.execute(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'collectai_readonly' AND table_name = 'account'"
        ).fetchall()
    assert {row[0] for row in rows} == {"SELECT"}


def test_no_role_has_any_grant_on_audit_event_because_it_does_not_exist_yet(
    migrated_schema: str,
) -> None:
    """audit_event is E1-S4's table; confirm this story truly leaves it alone."""
    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        ((exists,),) = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'audit_event')"
        ).fetchall()
    assert exists is False
