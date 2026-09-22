"""E1-S4 AC2: the application database role cannot UPDATE or DELETE
`audit_event` rows -- enforced at two layers: table grants (INSERT/SELECT
only) and a BEFORE UPDATE OR DELETE trigger that raises unconditionally,
even for a role that structurally owns the table."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.db

_INIT_ROLES_SQL_PATH = Path(__file__).resolve().parents[3] / "deploy" / "db" / "init-roles.sql"


def _sync_dsn(async_database_url: str) -> str:
    return async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _apply_roles_and_grant(conn: psycopg.Connection) -> None:
    from collectai.persistence.migrations._ddl_helpers import guarded_insert_select_grant_sql

    conn.execute(_INIT_ROLES_SQL_PATH.read_text(encoding="utf-8"))
    conn.execute(guarded_insert_select_grant_sql("audit_event"))


def _insert_one_row(conn: psycopg.Connection, audit_event_id: str) -> None:
    conn.execute(
        "INSERT INTO audit_event "
        "(audit_event_id, timestamp, correlation_id, stage, event_type, actor_kind) "
        "VALUES (%s, now(), 'c0ffee-grants-test', 'INPUT', 'CHAT_MESSAGE_RECEIVED', 'CUSTOMER')",
        (audit_event_id,),
    )


def test_collectai_app_can_insert_and_select_audit_event(migrated_schema: str) -> None:
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        _apply_roles_and_grant(conn)
        conn.execute("SET ROLE collectai_app")
        _insert_one_row(conn, "aud_GRANTSTESTINSERT01")
        rows = conn.execute(
            "SELECT audit_event_id FROM audit_event WHERE audit_event_id = %s",
            ("aud_GRANTSTESTINSERT01",),
        ).fetchall()
    assert rows == [("aud_GRANTSTESTINSERT01",)]


def test_collectai_app_update_on_audit_event_raises_permission_error(
    migrated_schema: str,
) -> None:
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        _apply_roles_and_grant(conn)
        _insert_one_row(conn, "aud_GRANTSTESTUPDATE01")
        conn.execute("SET ROLE collectai_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE audit_event SET final_action = 'x' WHERE audit_event_id = %s",
                ("aud_GRANTSTESTUPDATE01",),
            )


def test_collectai_app_delete_on_audit_event_raises_permission_error(
    migrated_schema: str,
) -> None:
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        _apply_roles_and_grant(conn)
        _insert_one_row(conn, "aud_GRANTSTESTDELETE01")
        conn.execute("SET ROLE collectai_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "DELETE FROM audit_event WHERE audit_event_id = %s",
                ("aud_GRANTSTESTDELETE01",),
            )


def test_trigger_blocks_update_even_for_the_owning_superuser_connection(
    migrated_schema: str,
) -> None:
    """Second layer of defence (data-models.md): the trigger raises
    regardless of the connecting role's grants, so a compromised or
    misconfigured grant alone would not be enough to mutate history."""
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        _insert_one_row(conn, "aud_GRANTSTESTTRIGGER1")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE audit_event SET final_action = 'x' WHERE audit_event_id = %s",
                ("aud_GRANTSTESTTRIGGER1",),
            )


def test_trigger_blocks_delete_even_for_the_owning_superuser_connection(
    migrated_schema: str,
) -> None:
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        _insert_one_row(conn, "aud_GRANTSTESTTRIGGER2")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "DELETE FROM audit_event WHERE audit_event_id = %s",
                ("aud_GRANTSTESTTRIGGER2",),
            )
