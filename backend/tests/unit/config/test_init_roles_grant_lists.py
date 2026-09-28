"""The readiness check `app_role_grants` and `deploy/db/init-roles.sql` must agree on which
tables are insert-only, or readiness would reject (or wave through) what the file grants."""

from __future__ import annotations

import re
from pathlib import Path

from collectai.domain_services.readiness_service import _INSERT_ONLY_TABLES

_SQL = (Path(__file__).resolve().parents[4] / "deploy" / "db" / "init-roles.sql").read_text(
    encoding="utf-8"
)


def _table_list(privileges: str, role: str) -> set[str]:
    match = re.search(
        rf"GRANT {privileges}\s+ON TABLE\s+(?P<tables>[^;]+?)\s+TO {role};", _SQL, re.DOTALL
    )
    assert match is not None, f"no `GRANT {privileges} ... TO {role}` in init-roles.sql"
    return {name.strip() for name in match["tables"].split(",") if name.strip()}


def test_readiness_insert_only_set_is_the_files_insert_only_grant_plus_audit_event() -> None:
    file_insert_only = _table_list("INSERT, SELECT", "collectai_app")

    # audit_event is granted by migration 0007, not by this file (which says so in a comment).
    assert _INSERT_ONLY_TABLES == file_insert_only | {"audit_event"}


def test_no_table_is_both_updatable_and_insert_only_in_the_file() -> None:
    updatable = _table_list("INSERT, SELECT, UPDATE", "collectai_app")

    assert updatable.isdisjoint(_INSERT_ONLY_TABLES)


def test_alembic_version_is_select_only_and_outside_the_business_table_scan() -> None:
    """`app_role_grants` (readiness_service.py) deliberately scans every public table except
    `alembic_version` -- migration state, not a business table (its own SQL says
    `tablename <> 'alembic_version'`). This file grants collectai_app SELECT only on it, via
    neither the ordinary nor the insert-only business-table list above, so it must stay out of
    `_INSERT_ONLY_TABLES` (that set feeds `app_role_grants`'s per-business-table checks)."""
    alembic_grant = _table_list("SELECT", "collectai_app")

    assert alembic_grant == {"alembic_version"}
    assert "alembic_version" not in _INSERT_ONLY_TABLES
