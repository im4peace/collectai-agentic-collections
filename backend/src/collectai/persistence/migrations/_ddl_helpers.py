"""Small string-building helpers shared by every migration revision.

Every table in data-models.md follows the same conventions (section 1): ids
are `text` with a prefix CHECK, money is `NUMERIC(14,2)`, enums are `text`
with a value-list CHECK, timestamps are `timestamptz`. Revision files call
these helpers instead of repeating the same CHECK/column boilerplate 23
times, which is also what keeps Rule 2 (bounded string fields, e.g. every
`policy_version` column) consistent: `policy_version_column()` is the single
place that bound is defined.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def id_column(name: str, prefix: str, *, nullable: bool = False, primary_key: bool = False) -> str:
    """A `text` id column with a prefix CHECK, e.g. `CHECK (col ~ '^cus_')`."""
    null_sql = "" if nullable else " NOT NULL"
    pk_sql = " PRIMARY KEY" if primary_key else ""
    return f"{name} text{null_sql}{pk_sql} CHECK ({name} ~ '^{prefix}_')"


def enum_check_column(name: str, values: Sequence[str], *, nullable: bool = True) -> str:
    """A `text` column with `CHECK (col IN (...))` built from enum members."""
    null_sql = "" if nullable else " NOT NULL"
    values_sql = ", ".join(f"'{value}'" for value in values)
    return f"{name} text{null_sql} CHECK ({name} IN ({values_sql}))"


def money_column(name: str, *, nullable: bool = False) -> str:
    """A `NUMERIC(14,2)` money column (data-models.md section 1)."""
    null_sql = "" if nullable else " NOT NULL"
    return f"{name} NUMERIC(14,2){null_sql}"


def policy_version_column(name: str = "policy_version", *, nullable: bool = False) -> str:
    """`text` bounded to 40 chars, per Rule 2 (learned-rules.md 2026-09-22)."""
    null_sql = "" if nullable else " NOT NULL"
    return f"{name} varchar(40){null_sql}"


def timestamptz_column(name: str, *, nullable: bool = True) -> str:
    null_sql = "" if nullable else " NOT NULL"
    return f"{name} timestamptz{null_sql}"


def create_table(name: str, columns: Iterable[str], *, extra: Iterable[str] = ()) -> str:
    """Join column and table-level constraint fragments into a CREATE TABLE."""
    all_fragments = list(columns) + list(extra)
    body = ",\n    ".join(all_fragments)
    return f"CREATE TABLE {name} (\n    {body}\n)"


def guarded_insert_select_grant_sql(table: str, *, role: str = "collectai_app") -> str:
    """A `GRANT INSERT, SELECT` on `table` to `role`, applied only if `role`
    already exists.

    Used by insert-only-table migrations (e.g. `audit_event`, 0007) that may
    run before `deploy/db/init-roles.sql` creates the application role (see
    `tests/db/conftest.py`'s `migrated_schema` fixture, which applies
    migrations alone). Exposed here (rather than inlined per-migration) so a
    test can execute the exact same SQL the migration runs, once the role
    does exist, without duplicating the string.
    """
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT INSERT, SELECT ON TABLE {table} TO {role};
            END IF;
        END
        $$
        """
