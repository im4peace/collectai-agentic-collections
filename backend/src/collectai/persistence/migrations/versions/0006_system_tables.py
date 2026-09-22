"""policy_rule_set, demo_session, idempotency_record, clock_state, eval_run,
eval_case_result

Revision ID: 0006_system_tables
Revises: 0005_escalation_review
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from collectai.persistence.migrations._ddl_helpers import (
    create_table,
    enum_check_column,
    id_column,
    policy_version_column,
    timestamptz_column,
)

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_PERSONAS = ("CUSTOMER", "COLLECTIONS_OFFICER", "COLLECTIONS_MANAGER", "COMPLIANCE_RISK")
_CLOCK_MODES = ("SYSTEM", "SIMULATED")
_PROVIDER_MODES = ("MOCK", "LIVE")

# Tables (created earlier) that carry a policy_version-shaped column FKing to
# policy_rule_set, which could not exist until this migration created it.
_POLICY_VERSION_FK_TARGETS: tuple[tuple[str, str], ...] = (
    ("promise_to_pay", "policy_version"),
    ("payment_arrangement", "policy_version"),
    ("proposal", "policy_version"),
    ("recommendation", "policy_version"),
    ("escalation_case", "routing_policy_version"),
    ("review_decision", "policy_version"),
)


def upgrade() -> None:
    _create_policy_rule_set_table()
    _create_demo_session_table()
    _create_idempotency_record_table()
    _create_clock_state_table()
    _create_eval_run_table()
    _create_eval_case_result_table()
    _add_policy_version_fks()


def downgrade() -> None:
    _drop_policy_version_fks()
    op.execute("DROP TABLE IF EXISTS eval_case_result")
    op.execute("DROP TABLE IF EXISTS eval_run")
    op.execute("DROP TABLE IF EXISTS clock_state")
    op.execute("DROP TABLE IF EXISTS idempotency_record")
    op.execute("DROP TABLE IF EXISTS demo_session")
    op.execute("DROP TABLE IF EXISTS policy_rule_set")


def _create_policy_rule_set_table() -> None:
    op.execute(
        create_table(
            "policy_rule_set",
            [
                "policy_version varchar(40) PRIMARY KEY",
                "parameters jsonb NOT NULL",
                "content_hash char(64) NOT NULL",
                "is_active boolean NOT NULL",
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("activated_at", nullable=True),
            ],
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_policy_rule_set_is_active ON policy_rule_set (is_active) "
        "WHERE is_active"
    )
    _create_policy_rule_set_immutability_trigger()


def _create_policy_rule_set_immutability_trigger() -> None:
    """Immutable except for the activation function (data-models.md
    PolicyRuleSet): a BEFORE UPDATE trigger rejects any change to
    `parameters` or `content_hash`; only `is_active`/`activated_at` may
    change."""
    op.execute(
        """
        CREATE FUNCTION policy_rule_set_guard_immutability() RETURNS trigger AS $$
        BEGIN
            IF NEW.parameters IS DISTINCT FROM OLD.parameters
                OR NEW.content_hash IS DISTINCT FROM OLD.content_hash THEN
                RAISE EXCEPTION
                    'policy_rule_set % is immutable: parameters and content_hash cannot change',
                    OLD.policy_version
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_policy_rule_set_guard_immutability
        BEFORE UPDATE ON policy_rule_set
        FOR EACH ROW
        EXECUTE FUNCTION policy_rule_set_guard_immutability()
        """
    )


def _create_demo_session_table() -> None:
    op.execute(
        create_table(
            "demo_session",
            [
                "session_token_hash char(64) PRIMARY KEY",
                enum_check_column("persona", _PERSONAS, nullable=False),
                id_column("customer_id", "cus", nullable=True),
                "display_name varchar(120) NOT NULL",
                timestamptz_column("issued_at", nullable=False),
                timestamptz_column("last_seen_at", nullable=False),
            ],
            extra=[
                "FOREIGN KEY (customer_id) REFERENCES customer (customer_id)",
                "CHECK ((persona = 'CUSTOMER') = (customer_id IS NOT NULL))",
            ],
        )
    )
    op.execute("CREATE INDEX ix_demo_session_customer_id ON demo_session (customer_id)")


def _create_idempotency_record_table() -> None:
    op.execute(
        create_table(
            "idempotency_record",
            [
                "idempotency_id bigserial PRIMARY KEY",
                "scope varchar(120) NOT NULL",
                "idempotency_key varchar(128) NOT NULL",
                "request_hash char(64) NOT NULL",
                "response_status integer NOT NULL",
                "response_body jsonb NOT NULL",
                "resource_type varchar(40)",
                "resource_id text",
                timestamptz_column("created_at", nullable=False),
            ],
            extra=["UNIQUE (scope, idempotency_key)"],
        )
    )
    op.execute("CREATE INDEX ix_idempotency_record_created_at ON idempotency_record (created_at)")


def _create_clock_state_table() -> None:
    op.execute(
        create_table(
            "clock_state",
            [
                "clock_state_id integer PRIMARY KEY CHECK (clock_state_id = 1)",
                enum_check_column("mode", _CLOCK_MODES, nullable=False),
                timestamptz_column("simulated_now", nullable=True),
                timestamptz_column("updated_at", nullable=False),
            ],
            extra=["CHECK ((mode = 'SIMULATED') = (simulated_now IS NOT NULL))"],
        )
    )


def _create_eval_run_table() -> None:
    op.execute(
        create_table(
            "eval_run",
            [
                id_column("eval_run_id", "evr", primary_key=True),
                enum_check_column("mode", _PROVIDER_MODES, nullable=False),
                "dataset_version varchar(40) NOT NULL",
                "dataset_provenance jsonb NOT NULL",
                "model_id varchar(120)",
                "prompt_version varchar(40) NOT NULL",
                policy_version_column(),
                timestamptz_column("run_at", nullable=False),
                "case_count integer NOT NULL",
                "intent_accuracy NUMERIC(9,4)",
                "metrics jsonb NOT NULL",
                "input_tokens integer",
                "output_tokens integer",
                "estimated_cost_usd NUMERIC(12,6)",
                "triggered_by varchar(60) NOT NULL",
            ],
            extra=[
                "FOREIGN KEY (policy_version) REFERENCES policy_rule_set (policy_version) "
                "ON DELETE RESTRICT",
                "CHECK (mode = 'LIVE' OR model_id IS NULL)",
            ],
        )
    )
    op.execute("CREATE INDEX ix_eval_run_mode_run_at ON eval_run (mode, run_at DESC)")
    op.execute("CREATE INDEX ix_eval_run_dataset_version ON eval_run (dataset_version)")


def _create_eval_case_result_table() -> None:
    op.execute(
        create_table(
            "eval_case_result",
            [
                id_column("eval_case_result_id", "evc", primary_key=True),
                id_column("eval_run_id", "evr"),
                "case_id varchar(60) NOT NULL",
                "category varchar(60) NOT NULL",
                "expected jsonb NOT NULL",
                "actual jsonb NOT NULL",
                "passed boolean NOT NULL",
                "critical_policy_violation boolean NOT NULL",
            ],
            extra=[
                "FOREIGN KEY (eval_run_id) REFERENCES eval_run (eval_run_id)",
            ],
        )
    )
    op.execute("CREATE INDEX ix_eval_case_result_eval_run_id ON eval_case_result (eval_run_id)")
    op.execute(
        "CREATE INDEX ix_eval_case_result_eval_run_category "
        "ON eval_case_result (eval_run_id, category)"
    )


def _add_policy_version_fks() -> None:
    for table_name, column_name in _POLICY_VERSION_FK_TARGETS:
        op.execute(
            f"ALTER TABLE {table_name} ADD CONSTRAINT fk_{table_name}_{column_name} "
            f"FOREIGN KEY ({column_name}) REFERENCES policy_rule_set (policy_version) "
            "ON DELETE RESTRICT"
        )


def _drop_policy_version_fks() -> None:
    for table_name, column_name in _POLICY_VERSION_FK_TARGETS:
        op.execute(
            f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS fk_{table_name}_{column_name}"
        )
