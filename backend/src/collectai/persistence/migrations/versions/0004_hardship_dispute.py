"""hardship_case, dispute

Revision ID: 0004_hardship_dispute
Revises: 0003_ptp_payment_arrangement
Create Date: 2026-09-22

`escalation_case_id` on both tables is added as a plain nullable column here;
its FK constraint is added by revision 0005 once `escalation_case` exists
(data-models.md section 2 ERD has `hardship_case`/`dispute` and
`escalation_case` reference each other, so one direction must be deferred).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from collectai.persistence.migrations._ddl_helpers import (
    create_table,
    enum_check_column,
    id_column,
    timestamptz_column,
)

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_HARDSHIP_STATUSES = ("OPEN", "UNDER_REVIEW", "DECIDED")
_DISPUTE_CATEGORIES = (
    "AMOUNT_INCORRECT",
    "NOT_MY_DEBT",
    "ALREADY_PAID",
    "FRAUD_OR_UNAUTHORIZED",
    "FEE_OR_INTEREST_DISPUTE",
    "OTHER",
)
_DISPUTE_STATUSES = ("OPEN", "UNDER_REVIEW", "RESOLVED")
_DISPUTE_OUTCOMES = ("UPHELD", "REJECTED", "WITHDRAWN")


def upgrade() -> None:
    _create_hardship_case_table()
    _create_dispute_table()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dispute")
    op.execute("DROP TABLE IF EXISTS hardship_case")


def _create_hardship_case_table() -> None:
    # escalation_case_id's FK is added by 0005's _add_deferred_escalation_case_fks.
    op.execute(
        create_table(
            "hardship_case",
            [
                id_column("hardship_case_id", "hsp", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                id_column("conversation_id", "conv", nullable=True),
                enum_check_column("status", _HARDSHIP_STATUSES, nullable=False),
                "indicators jsonb NOT NULL",
                id_column("escalation_case_id", "esc", nullable=True),
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("decided_at", nullable=True),
                timestamptz_column("updated_at", nullable=False),
                "version integer NOT NULL DEFAULT 1",
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id)",
                "CHECK (jsonb_array_length(indicators) >= 1)",
            ],
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_hardship_case_open_per_account ON hardship_case (account_id) "
        "WHERE status <> 'DECIDED'"
    )
    op.execute("CREATE INDEX ix_hardship_case_customer_id ON hardship_case (customer_id)")


def _create_dispute_table() -> None:
    # escalation_case_id's FK is added by 0005's _add_deferred_escalation_case_fks.
    op.execute(
        create_table(
            "dispute",
            [
                id_column("dispute_id", "dsp", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                id_column("item_id", "itm", nullable=True),
                enum_check_column("category", _DISPUTE_CATEGORIES, nullable=False),
                "customer_reason varchar(1000) NOT NULL",
                enum_check_column("status", _DISPUTE_STATUSES, nullable=False),
                enum_check_column("outcome", _DISPUTE_OUTCOMES),
                "resolution_reason varchar(1000)",
                id_column("conversation_id", "conv", nullable=True),
                id_column("escalation_case_id", "esc", nullable=True),
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("resolved_at", nullable=True),
                timestamptz_column("updated_at", nullable=False),
                "version integer NOT NULL DEFAULT 1",
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "FOREIGN KEY (item_id) REFERENCES delinquent_item (item_id)",
                "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id)",
                "CHECK ((status = 'RESOLVED') = (outcome IS NOT NULL "
                "AND resolution_reason IS NOT NULL AND resolved_at IS NOT NULL))",
            ],
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_dispute_open_per_scope ON dispute "
        "(account_id, COALESCE(item_id, 'ACCOUNT')) WHERE status <> 'RESOLVED'"
    )
    op.execute("CREATE INDEX ix_dispute_customer_id ON dispute (customer_id)")
    op.execute("CREATE INDEX ix_dispute_item_id ON dispute (item_id) WHERE status <> 'RESOLVED'")
