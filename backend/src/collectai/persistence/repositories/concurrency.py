"""Shared optimistic-concurrency update helper (data-models.md section 1):
`UPDATE ... SET version = version + 1 WHERE id = :id AND version = :expected`;
zero rows updated means a conflict. Every versioned entity's repository
reuses this instead of hand-rolling the same WHERE-and-count pattern.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, Table, update
from sqlalchemy.ext.asyncio import AsyncSession


async def optimistic_update(
    session: AsyncSession,
    table: Table,
    *,
    pk_conditions: dict[str, Any],
    version_column: str,
    expected_version: int,
    values: dict[str, Any],
) -> bool:
    """Apply `values` to the row matching `pk_conditions` and
    `version_column == expected_version`. Returns `True` iff exactly one row
    was updated; `False` means either the row does not exist or another
    writer already advanced its version (a 409 VERSION_CONFLICT, for the
    caller to raise)."""
    conditions = [table.c[column] == value for column, value in pk_conditions.items()]
    conditions.append(table.c[version_column] == expected_version)
    statement = update(table).where(*conditions).values(**values)
    result = cast(CursorResult[Any], await session.execute(statement))
    return (result.rowcount or 0) == 1
