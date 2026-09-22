"""E1-S5 AC1/AC2: `GET /api/ready` (via `domain_services.readiness_service`)
reports database, migrations, policy_ruleset and audit_role_grants checks
against a real PostgreSQL instance. Lives in `tests/db` (not `tests/unit`)
because every check requires a real database, matching the convention in
`tests/db/test_e1_s3_delinquency_repository.py`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.domain_services.readiness_service import check_readiness

pytestmark = pytest.mark.db


async def _insert_active_policy(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-ready-test', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"created_at": datetime.now(UTC)},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_check_readiness_reports_database_ok(session: AsyncSession, clean_db: None) -> None:
    result = await check_readiness(session)
    database_check = next(c for c in result.checks if c.name == "database")
    assert database_check.ok is True


@pytest.mark.asyncio
async def test_check_readiness_reports_migrations_ok_after_migrate(
    session: AsyncSession, clean_db: None
) -> None:
    result = await check_readiness(session)
    migrations_check = next(c for c in result.checks if c.name == "migrations")
    assert migrations_check.ok is True


@pytest.mark.asyncio
async def test_check_readiness_policy_ruleset_not_ok_when_no_active_row(
    session: AsyncSession, clean_db: None
) -> None:
    await session.execute(text("DELETE FROM policy_rule_set"))
    await session.commit()
    result = await check_readiness(session)
    policy_check = next(c for c in result.checks if c.name == "policy_ruleset")
    assert policy_check.ok is False
    assert result.ready is False


@pytest.mark.asyncio
async def test_check_readiness_policy_ruleset_ok_with_exactly_one_active_row(
    session: AsyncSession, clean_db: None
) -> None:
    await session.execute(text("DELETE FROM policy_rule_set"))
    await session.commit()
    await _insert_active_policy(session)
    result = await check_readiness(session)
    policy_check = next(c for c in result.checks if c.name == "policy_ruleset")
    assert policy_check.ok is True


@pytest.mark.asyncio
async def test_check_readiness_audit_role_grants_not_ok_before_audit_migration_or_grants(
    session: AsyncSession, clean_db: None
) -> None:
    """If audit_event does not exist, or collectai_app has no grants row on
    it yet, the check must fail closed with a safe detail, never raise.

    Explicitly revokes first: `migrated_schema`/`pg_server` are
    session-scoped fixtures shared with `tests/db/test_e1_s4_audit_grants.py`
    and `test_e1_s3_init_roles.py`, both of which create `collectai_app` and
    grant it INSERT/SELECT on `audit_event` as a real, session-lifetime role
    privilege (not undone by `clean_db`'s table truncation). Revoking here
    makes this test's "not granted yet" precondition true regardless of
    what ran earlier in the same test session.
    """
    await session.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collectai_app') THEN "
            "REVOKE ALL ON TABLE audit_event FROM collectai_app; "
            "END IF; END $$"
        )
    )
    await session.commit()

    result = await check_readiness(session)
    audit_check = next(c for c in result.checks if c.name == "audit_role_grants")
    assert audit_check.ok is False
    assert audit_check.detail is not None


@pytest.mark.asyncio
async def test_check_readiness_does_not_raise_and_session_stays_usable_after_missing_table(
    session: AsyncSession, clean_db: None
) -> None:
    """A failed audit_event lookup must not poison the session for the
    checks that run after it (or before it, depending on ordering)."""
    result = await check_readiness(session)
    assert isinstance(result.ready, bool)
    # The session must still be usable for a subsequent query.
    await session.execute(text("SELECT 1"))


@pytest.mark.asyncio
async def test_check_readiness_ready_true_only_when_every_check_ok(
    session: AsyncSession, clean_db: None
) -> None:
    await session.execute(text("DELETE FROM policy_rule_set"))
    await session.commit()
    result = await check_readiness(session)
    assert result.ready is False
    assert any(not c.ok for c in result.checks)
