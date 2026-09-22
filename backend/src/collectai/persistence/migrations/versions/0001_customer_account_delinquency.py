"""customer, account, delinquency_record, delinquent_item, interaction

Revision ID: 0001_customer_account_delinquency
Revises:
Create Date: 2026-09-22

NOTE: nearing the 300-line block threshold (5 tables, each with DDL, indexes
and one trigger). If a future migration adds columns here, prefer a new
revision file rather than growing this one further.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from collectai.persistence.migrations._ddl_helpers import (
    create_table,
    enum_check_column,
    id_column,
    money_column,
    timestamptz_column,
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_ACCOUNT_TYPES = ("CARD", "PERSONAL_LOAN")
_VULNERABILITY_CATEGORIES = (
    "BEREAVEMENT",
    "SERIOUS_ILLNESS_OR_DISABILITY",
    "MENTAL_HEALTH_CONCERN",
    "DOMESTIC_ABUSE_OR_COERCION",
    "LIMITED_CAPACITY_TO_UNDERSTAND",
    "LANGUAGE_OR_COMMUNICATION_BARRIER",
    "OTHER",
)
_BUCKETS = ("CURRENT", "DPD_1_29", "DPD_30_59", "DPD_60_89", "DPD_90_PLUS")
_COLLECTION_STATUSES = (
    "NEW",
    "IN_PROGRESS",
    "PTP_PENDING",
    "ARRANGEMENT_ACTIVE",
    "ESCALATED",
    "RESOLVED",
)
_ITEM_KINDS = ("INSTALLMENT", "STATEMENT_CYCLE", "FEE_OR_CHARGE")
_ITEM_STATUSES = ("OPEN", "PAID")
_INTERACTION_CHANNELS = (
    "SIMULATED_CHAT",
    "SIMULATED_OUTBOUND_CALL",
    "SIMULATED_OUTBOUND_MESSAGE",
    "SYSTEM_EVENT",
)
_INTERACTION_DIRECTIONS = ("INBOUND", "OUTBOUND", "INTERNAL")
_CONTACT_OUTCOMES = (
    "NO_CONTACT",
    "CONTACT_NO_COMMITMENT",
    "PTP_MADE",
    "PTP_BROKEN",
    "PAYMENT_MADE",
)


def upgrade() -> None:
    _create_customer_table()
    _create_account_table()
    _create_delinquency_record_table()
    _create_delinquent_item_table()
    _create_interaction_table()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS interaction")
    op.execute("DROP TABLE IF EXISTS delinquent_item")
    op.execute("DROP TABLE IF EXISTS delinquency_record")
    op.execute("DROP TABLE IF EXISTS account")
    op.execute("DROP TABLE IF EXISTS customer")


def _create_customer_table() -> None:
    op.execute(
        create_table(
            "customer",
            [
                id_column("customer_id", "cus", primary_key=True),
                "display_name varchar(120) NOT NULL",
                "email text NOT NULL",
                "phone text NOT NULL",
                "vulnerability_flag boolean NOT NULL DEFAULT false",
                enum_check_column("vulnerability_category", _VULNERABILITY_CATEGORIES),
                id_column("vulnerability_case_id", "esc", nullable=True),
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("updated_at", nullable=False),
            ],
            extra=["CHECK (vulnerability_flag OR vulnerability_category IS NULL)"],
        )
    )
    op.execute(
        "CREATE INDEX ix_customer_vulnerability_flag ON customer (vulnerability_flag) "
        "WHERE vulnerability_flag"
    )


def _create_account_table() -> None:
    op.execute(
        create_table(
            "account",
            [
                id_column("account_id", "acc", primary_key=True),
                id_column("customer_id", "cus"),
                enum_check_column("account_type", _ACCOUNT_TYPES, nullable=False),
                "product_name varchar(120) NOT NULL",
                "currency text NOT NULL CHECK (currency = 'USD')",
                "opened_on date NOT NULL",
                "product_attributes jsonb NOT NULL",
                timestamptz_column("created_at", nullable=False),
            ],
            extra=[
                "FOREIGN KEY (customer_id) REFERENCES customer (customer_id) ON DELETE RESTRICT",
                "UNIQUE (account_id, customer_id)",
            ],
        )
    )
    op.execute("CREATE INDEX ix_account_customer_id ON account (customer_id)")


def _create_delinquency_record_table() -> None:
    op.execute(
        create_table(
            "delinquency_record",
            [
                id_column("account_id", "acc", primary_key=True),
                id_column("customer_id", "cus"),
                money_column("outstanding_balance"),
                money_column("overdue_amount"),
                "dpd integer NOT NULL",
                enum_check_column("bucket", _BUCKETS, nullable=False),
                enum_check_column("collection_status", _COLLECTION_STATUSES, nullable=False),
                timestamptz_column("as_of", nullable=True),
                "record_version integer NOT NULL DEFAULT 1",
                timestamptz_column("updated_at", nullable=False),
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "CHECK (outstanding_balance >= 0 AND overdue_amount >= 0 AND dpd >= 0)",
            ],
        )
    )
    op.execute("CREATE INDEX ix_delinquency_record_customer_id ON delinquency_record (customer_id)")
    op.execute(
        "CREATE INDEX ix_delinquency_record_dpd ON delinquency_record (dpd) "
        "WHERE overdue_amount > 0"
    )
    op.execute(
        "CREATE INDEX ix_delinquency_record_overdue_amount ON delinquency_record (overdue_amount) "
        "WHERE overdue_amount > 0"
    )
    op.execute(
        "CREATE INDEX ix_delinquency_record_collection_status "
        "ON delinquency_record (collection_status)"
    )
    op.execute("CREATE INDEX ix_delinquency_record_bucket ON delinquency_record (bucket)")
    _create_delinquency_record_version_trigger()


def _create_delinquency_record_version_trigger() -> None:
    """AC7 defence in depth: a BEFORE UPDATE trigger forces monotonic
    `record_version`, independent of whether the application remembered to
    increment it. The repository (AC7's primary path) sets it explicitly too."""
    op.execute(
        """
        CREATE FUNCTION delinquency_record_bump_version() RETURNS trigger AS $$
        BEGIN
            NEW.record_version := OLD.record_version + 1;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_delinquency_record_bump_version
        BEFORE UPDATE ON delinquency_record
        FOR EACH ROW
        EXECUTE FUNCTION delinquency_record_bump_version()
        """
    )


def _create_delinquent_item_table() -> None:
    op.execute(
        create_table(
            "delinquent_item",
            [
                id_column("item_id", "itm", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                enum_check_column("kind", _ITEM_KINDS, nullable=False),
                "label varchar(120) NOT NULL",
                money_column("amount_outstanding"),
                "due_date date NOT NULL",
                enum_check_column("status", _ITEM_STATUSES, nullable=False),
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "CHECK (amount_outstanding >= 0)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_delinquent_item_account_status ON delinquent_item (account_id, status)"
    )
    op.execute("CREATE INDEX ix_delinquent_item_customer_id ON delinquent_item (customer_id)")


def _create_interaction_table() -> None:
    # conversation_id references the `conversation` table created in
    # migration 0002; the column is created here without the FK, which
    # migration 0002 adds via ALTER TABLE once `conversation` exists.
    op.execute(
        create_table(
            "interaction",
            [
                id_column("interaction_id", "int", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                enum_check_column("channel", _INTERACTION_CHANNELS, nullable=False),
                enum_check_column("direction", _INTERACTION_DIRECTIONS, nullable=False),
                enum_check_column("outcome", _CONTACT_OUTCOMES),
                timestamptz_column("occurred_at", nullable=False),
                "summary varchar(500) NOT NULL",
                "counts_as_attempt boolean NOT NULL",
                id_column("conversation_id", "conv", nullable=True),
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_interaction_account_occurred_at "
        "ON interaction (account_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_interaction_account_attempt ON interaction (account_id, occurred_at) "
        "WHERE counts_as_attempt"
    )
