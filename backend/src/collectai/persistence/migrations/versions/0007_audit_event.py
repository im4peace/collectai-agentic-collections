"""audit_event: append-only audit table, grants and immutability trigger
(E1-S4 AC1, AC2).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from collectai.persistence.migrations._ddl_helpers import (
    create_table,
    enum_check_column,
    guarded_insert_select_grant_sql,
    id_column,
    policy_version_column,
    timestamptz_column,
)

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STAGES = (
    "INPUT",
    "AI_INTERPRETATION",
    "PROPOSAL",
    "RULE_VALIDATION",
    "HUMAN_DECISION",
    "FINAL_STATE",
)
_ACTOR_KINDS = ("CUSTOMER", "STAFF", "SYSTEM", "AI")
_PERSONAS = ("CUSTOMER", "COLLECTIONS_OFFICER", "COLLECTIONS_MANAGER", "COMPLIANCE_RISK")
_PROVIDER_MODES = ("MOCK", "LIVE")


def upgrade() -> None:
    _create_audit_event_table()
    _create_audit_event_indexes()
    _grant_app_role_insert_select()
    _create_audit_event_immutability_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_event_guard_immutability ON audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_guard_immutability()")
    op.execute("DROP TABLE IF EXISTS audit_event")


def _create_audit_event_table() -> None:
    op.execute(
        create_table(
            "audit_event",
            [
                id_column("audit_event_id", "aud", primary_key=True),
                "sequence bigint GENERATED ALWAYS AS IDENTITY",
                timestamptz_column("timestamp", nullable=False),
                "correlation_id varchar(64) NOT NULL",
                enum_check_column("stage", _STAGES, nullable=False),
                "event_type varchar(80) NOT NULL",
                enum_check_column("actor_kind", _ACTOR_KINDS, nullable=False),
                enum_check_column("actor_persona", _PERSONAS, nullable=True),
                id_column("customer_id", "cus", nullable=True),
                id_column("account_id", "acc", nullable=True),
                "capability varchar(40)",
                "provider varchar(40)",
                enum_check_column("provider_mode", _PROVIDER_MODES, nullable=True),
                "model_id varchar(120)",
                policy_version_column("prompt_version", nullable=True),
                policy_version_column("policy_version", nullable=True),
                "input_ref text",
                "ai_output jsonb",
                "tool_calls jsonb NOT NULL DEFAULT '[]'::jsonb",
                "rule_results jsonb",
                "human_override jsonb",
                "final_action varchar(120)",
                "reason_code varchar(60)",
                "resource_type varchar(40)",
                "resource_id text",
                "latency jsonb",
                "token_usage jsonb",
            ],
            extra=["UNIQUE (sequence)"],
        )
    )


def _create_audit_event_indexes() -> None:
    op.execute(
        "CREATE INDEX ix_audit_event_correlation_id "
        "ON audit_event (correlation_id, timestamp, sequence)"
    )
    op.execute("CREATE INDEX ix_audit_event_account_id ON audit_event (account_id, timestamp)")
    op.execute("CREATE INDEX ix_audit_event_customer_id ON audit_event (customer_id, timestamp)")
    op.execute("CREATE INDEX ix_audit_event_event_type ON audit_event (event_type, timestamp)")
    op.execute("CREATE INDEX ix_audit_event_timestamp ON audit_event (timestamp)")


def _grant_app_role_insert_select() -> None:
    """INSERT and SELECT only (AC2) -- never UPDATE or DELETE. Guarded by a
    role-existence check: this migration can run in a test database before
    `deploy/db/init-roles.sql` has created `collectai_app` (see
    `tests/db/conftest.py`'s `migrated_schema` fixture, which runs
    migrations alone), and a GRANT to a nonexistent role would fail the
    migration outright. In real deployment (docker-compose), the Postgres
    image runs `init-roles.sql` on first container init, before the
    `migrate` service ever connects, so the role always exists by the time
    this runs (deployment.md section 2). No explicit sequence grant is
    needed: unlike a plain SERIAL column, a `GENERATED ... AS IDENTITY`
    column's sequence is used implicitly by table INSERT privilege alone."""
    op.execute(guarded_insert_select_grant_sql("audit_event"))


def _create_audit_event_immutability_trigger() -> None:
    """Second layer of append-only enforcement (data-models.md: "A BEFORE
    UPDATE OR DELETE trigger raises as a second layer"): blocks UPDATE and
    DELETE unconditionally, for every role, independent of table grants."""
    op.execute(
        """
        CREATE FUNCTION audit_event_guard_immutability() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only: % is not permitted', TG_OP
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_guard_immutability
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW
        EXECUTE FUNCTION audit_event_guard_immutability()
        """
    )
