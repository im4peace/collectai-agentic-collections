"""Make chat_message's turn_id FK DEFERRABLE INITIALLY DEFERRED (E6-S1/
E6-S2/E6-S3, Group G integration finding).

`chat_message` and `chat_turn` reference each other (0002's own docstring),
so writing one turn's two messages plus its `chat_turn` row needs either an
UPDATE on `chat_message` after the fact, or a deferred FK check. `collectai
_app` is deliberately never granted UPDATE on `chat_message` (deploy/db
/init-roles.sql: "insert-only... so a compromised or buggy app process can
never rewrite history") -- an UPDATE-based insert order can therefore never
work against that role, only against a superuser/owner connection, which is
exactly why this only surfaced running the app as `collectai_app` against a
real Postgres instance rather than through pytest's own (unrestricted)
`embedded_postgres` fixture.

Making `fk_chat_message_turn` deferrable lets `application._chat_persistence
.persist_turn` insert both `chat_message` rows with `turn_id` already set
-- pointing at a `chat_turn` row that does not exist yet -- and insert that
`chat_turn` row before the transaction commits; the FK is checked at COMMIT,
by which point it is satisfied. No UPDATE on `chat_message` is issued at
all, preserving the insert-only grant exactly as before.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chat_message ALTER CONSTRAINT fk_chat_message_turn "
        "DEFERRABLE INITIALLY DEFERRED"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE chat_message ALTER CONSTRAINT fk_chat_message_turn "
        "NOT DEFERRABLE INITIALLY IMMEDIATE"
    )
