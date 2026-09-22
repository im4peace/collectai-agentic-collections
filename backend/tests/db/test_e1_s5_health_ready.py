"""E1-S5 AC1/AC2: `GET /api/health` and `GET /api/ready` against a real,
migrated database. Lives in `tests/db` (not a separate `tests/api`) because
it needs the `migrated_schema`/`session` fixtures from `tests/db/conftest.py`;
a future API-testing story (e.g. E3-S1) can introduce its own `tests/api/`
package with a conftest that reuses these fixtures once RBAC/persona
resolution needs its own test scaffolding.

Every test sets up its own preconditions explicitly rather than relying on
ambient state left by other tests sharing the session-scoped `migrated_schema`
database (`policy_rule_set` and role grants are not covered by the
`clean_db` truncation fixture, which only covers business tables)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.api.app import create_app
from collectai.config.settings import load_settings

pytestmark = pytest.mark.db

_INIT_ROLES_SQL_PATH = (
    Path(__file__).resolve().parents[3] / "deploy" / "db" / "init-roles.sql"
)


def _sync_dsn(async_database_url: str) -> str:
    return async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _build_test_client(database_url: str) -> TestClient:
    settings = load_settings({"DATABASE_URL": database_url})
    app = create_app(settings)
    return TestClient(app)


async def _ensure_one_active_policy(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM policy_rule_set"))
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-ready-test', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at)"
        ),
        {"created_at": datetime.now(UTC)},
    )
    await session.commit()


def _apply_init_roles(migrated_schema: str) -> None:
    """asyncpg (via SQLAlchemy) cannot run this file's multi-statement `DO
    $$ ... $$` block in one `execute`; use `psycopg` directly, matching
    `tests/db/test_e1_s3_init_roles.py`'s own approach.

    Also re-runs `audit_event`'s guarded grant (`_ddl_helpers
    .guarded_insert_select_grant_sql`, exposed by E1-S4 for exactly this):
    migration 0007 grants `collectai_app` INSERT/SELECT on `audit_event`
    only if that role already exists at migration time, which it does not
    in `migrated_schema` (a session-scoped fixture that runs migrations
    before any test creates roles). In real deployment, `init-roles.sql`
    runs before `migrate` (deployment.md section 2), so this ordering
    quirk is test-only — see `tests/db/test_e1_s4_audit_grants.py`'s
    `_apply_roles_and_grant`, which this mirrors."""
    from collectai.persistence.migrations._ddl_helpers import guarded_insert_select_grant_sql

    sql = _INIT_ROLES_SQL_PATH.read_text(encoding="utf-8")
    with psycopg.connect(_sync_dsn(migrated_schema), autocommit=True) as conn:
        conn.execute(sql)
        conn.execute(guarded_insert_select_grant_sql("audit_event"))


def test_get_health_returns_ok_without_touching_the_database(migrated_schema: str) -> None:
    with _build_test_client(migrated_schema) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_get_ready_returns_200_ready_when_policy_active_and_grants_applied(
    migrated_schema: str, session: AsyncSession
) -> None:
    await _ensure_one_active_policy(session)
    _apply_init_roles(migrated_schema)

    with _build_test_client(migrated_schema) as client:
        response = client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert all(check["ok"] for check in body["checks"])


@pytest.mark.asyncio
async def test_get_ready_returns_503_not_ready_when_no_active_policy(
    migrated_schema: str, session: AsyncSession
) -> None:
    _apply_init_roles(migrated_schema)
    await session.execute(text("DELETE FROM policy_rule_set"))
    await session.commit()

    with _build_test_client(migrated_schema) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    policy_check = next(c for c in body["checks"] if c["name"] == "policy_ruleset")
    assert policy_check["ok"] is False
