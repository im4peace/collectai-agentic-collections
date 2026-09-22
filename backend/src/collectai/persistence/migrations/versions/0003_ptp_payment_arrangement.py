"""promise_to_pay, payment_event, payment_arrangement

Revision ID: 0003_ptp_payment_arrangement
Revises: 0002_conversation_chat
Create Date: 2026-09-22

NOTE: nearing the 300-line block threshold. `policy_version` FKs to
`policy_rule_set` are added later, by migration 0006, once that table exists
(see the ALTER TABLE block at the end of 0006).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from collectai.persistence.migrations._ddl_helpers import (
    create_table,
    enum_check_column,
    id_column,
    money_column,
    policy_version_column,
    timestamptz_column,
)

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_PTP_STATUSES = ("PENDING", "KEPT", "BROKEN", "CANCELLED")
_PTP_SOURCES = ("OFFICER_MANUAL", "CUSTOMER_CHAT")
_PERSONAS = ("CUSTOMER", "COLLECTIONS_OFFICER", "COLLECTIONS_MANAGER", "COMPLIANCE_RISK")
_PAYMENT_OUTCOMES = ("SUCCEEDED", "FAILED")
_PAYMENT_SOURCES = ("CUSTOMER_CHAT", "DEMO_CONTROL")
_ARRANGEMENT_STATUSES = ("ACTIVE", "COMPLETED", "CANCELLED")
_ARRANGEMENT_CREATED_VIA = ("CUSTOMER_CONFIRMATION", "EXCEPTION_APPROVAL")


def upgrade() -> None:
    _create_promise_to_pay_table()
    _create_ptp_transition_guard_trigger()
    _create_payment_event_table()
    _create_payment_arrangement_table()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payment_arrangement")
    op.execute("DROP TABLE IF EXISTS payment_event")
    op.execute("DROP TABLE IF EXISTS promise_to_pay")


def _create_promise_to_pay_table() -> None:
    op.execute(
        create_table(
            "promise_to_pay",
            [
                id_column("ptp_id", "ptp", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                id_column("item_id", "itm", nullable=True),
                money_column("promised_amount"),
                "promised_date date NOT NULL",
                enum_check_column("status", _PTP_STATUSES, nullable=False),
                money_column("cumulative_paid"),
                "interaction_reference text",
                enum_check_column("source", _PTP_SOURCES, nullable=False),
                enum_check_column("created_by_persona", _PERSONAS, nullable=False),
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("updated_at", nullable=False),
                timestamptz_column("kept_at", nullable=True),
                timestamptz_column("broken_at", nullable=True),
                timestamptz_column("cancelled_at", nullable=True),
                "cancel_reason varchar(500)",
                policy_version_column(),
                "version integer NOT NULL DEFAULT 1",
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "FOREIGN KEY (item_id) REFERENCES delinquent_item (item_id)",
                "CHECK (promised_amount > 0 AND cumulative_paid >= 0)",
                "CHECK (status <> 'KEPT' OR kept_at IS NOT NULL)",
                "CHECK (status <> 'BROKEN' OR broken_at IS NOT NULL)",
                "CHECK (status <> 'CANCELLED' OR "
                "(cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL))",
            ],
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_promise_to_pay_pending_per_account ON promise_to_pay (account_id) "
        "WHERE status = 'PENDING'"
    )
    op.execute("CREATE INDEX ix_promise_to_pay_customer_id ON promise_to_pay (customer_id)")
    op.execute(
        "CREATE INDEX ix_promise_to_pay_status_date ON promise_to_pay (status, promised_date) "
        "WHERE status = 'PENDING'"
    )


def _create_ptp_transition_guard_trigger() -> None:
    """Defence in depth for the PENDING -> {KEPT, BROKEN, CANCELLED} state
    machine (data-models.md section 4.3): rejects any UPDATE whose OLD.status
    is not PENDING and whose NEW.status differs. The domain service checks
    this first; the trigger protects the schema regardless of which future
    story is first to write PTPs."""
    op.execute(
        """
        CREATE FUNCTION promise_to_pay_guard_transition() RETURNS trigger AS $$
        BEGIN
            IF OLD.status <> 'PENDING' AND NEW.status <> OLD.status THEN
                RAISE EXCEPTION
                    'promise_to_pay % cannot transition from % to %: only PENDING may transition',
                    OLD.ptp_id, OLD.status, NEW.status
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_promise_to_pay_guard_transition
        BEFORE UPDATE ON promise_to_pay
        FOR EACH ROW
        EXECUTE FUNCTION promise_to_pay_guard_transition()
        """
    )


def _create_payment_event_table() -> None:
    op.execute(
        create_table(
            "payment_event",
            [
                id_column("payment_event_id", "pay", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                money_column("amount"),
                enum_check_column("outcome", _PAYMENT_OUTCOMES, nullable=False),
                enum_check_column("source", _PAYMENT_SOURCES, nullable=False),
                "simulated boolean NOT NULL",
                timestamptz_column("occurred_at", nullable=False),
                money_column("balance_after"),
                id_column("applied_to_ptp_id", "ptp", nullable=True),
                id_column("proposal_id", "prp", nullable=True),
                enum_check_column("created_by_persona", _PERSONAS, nullable=False),
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "FOREIGN KEY (applied_to_ptp_id) REFERENCES promise_to_pay (ptp_id)",
                "FOREIGN KEY (proposal_id) REFERENCES proposal (proposal_id)",
                "CHECK (simulated IS TRUE)",
                "CHECK (amount > 0 AND balance_after >= 0)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_payment_event_account_occurred ON payment_event (account_id, occurred_at)"
    )
    op.execute("CREATE INDEX ix_payment_event_customer_id ON payment_event (customer_id)")
    op.execute(
        "CREATE UNIQUE INDEX ux_payment_event_proposal_id ON payment_event (proposal_id) "
        "WHERE proposal_id IS NOT NULL"
    )


def _create_payment_arrangement_table() -> None:
    # exception_case_id's FK to escalation_case is added by migration 0004.
    op.execute(
        create_table(
            "payment_arrangement",
            [
                id_column("arrangement_id", "arr", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                enum_check_column("status", _ARRANGEMENT_STATUSES, nullable=False),
                enum_check_column("created_via", _ARRANGEMENT_CREATED_VIA, nullable=False),
                id_column("exception_case_id", "esc", nullable=True),
                "option_id varchar(80) NOT NULL",
                "installment_count integer NOT NULL",
                money_column("installment_amount"),
                money_column("final_installment_amount"),
                money_column("total_amount"),
                "first_installment_date date NOT NULL",
                "frequency text NOT NULL CHECK (frequency = 'MONTHLY')",
                "schedule jsonb NOT NULL",
                policy_version_column(),
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("updated_at", nullable=False),
                "version integer NOT NULL DEFAULT 1",
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
                "CHECK ((created_via = 'EXCEPTION_APPROVAL') = (exception_case_id IS NOT NULL))",
            ],
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_payment_arrangement_active_per_account "
        "ON payment_arrangement (account_id) WHERE status = 'ACTIVE'"
    )
    op.execute(
        "CREATE INDEX ix_payment_arrangement_customer_id ON payment_arrangement (customer_id)"
    )
