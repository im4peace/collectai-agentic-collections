"""escalation_case, review_decision

Revision ID: 0005_escalation_review
Revises: 0004_hardship_dispute
Create Date: 2026-09-22

`hardship_case` and `dispute` (revision 0004) each reference
`escalation_case`, and `escalation_case` references both of them back
(data-models.md section 2 ERD), so the two `escalation_case_id` FKs are
added via ALTER TABLE after `escalation_case` exists here, breaking the
circularity. Several other tables created by earlier migrations also gained
a nullable FK column pointing at `escalation_case` before it existed
(`customer.vulnerability_case_id`, `proposal.case_id`,
`payment_arrangement.exception_case_id`); their FKs are added here too.
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

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_ESCALATION_REASONS = (
    "REQUEST_HUMAN",
    "UNRESOLVED_UNKNOWN",
    "AI_FAILURE_FALLBACK",
    "EXCEPTIONAL_ARRANGEMENT",
    "FINANCIAL_HARDSHIP",
    "DISPUTE",
    "SETTLEMENT_REQUEST",
    "AMBIGUOUS_VALIDATION",
    "VULNERABLE_CUSTOMER",
    "POLICY_EXCEPTION",
    "HIGH_RISK_COMPLIANCE",
)
_REVIEW_QUEUES = (
    "COLLECTIONS_REVIEW",
    "COLLECTIONS_EXCEPTION_REVIEW",
    "HARDSHIP_REVIEW",
    "DISPUTE_REVIEW",
    "VULNERABLE_CUSTOMER_REVIEW",
    "COMPLIANCE_REVIEW",
)
_REVIEWER_ROLES = ("COLLECTIONS_OFFICER", "COMPLIANCE_RISK")
_ESCALATION_PRIORITIES = ("NORMAL", "ELEVATED", "URGENT")
_CASE_STATUSES = ("OPEN", "IN_REVIEW", "AWAITING_INFORMATION", "DECIDED", "RE_ROUTED")
_CASE_SOURCES = ("AI", "CUSTOMER", "SYSTEM", "REVIEWER")
_DECISION_KINDS = ("REVIEWER_ACTION", "COMPLIANCE_DECISION", "START_REVIEW")
_REVIEW_ACTIONS = ("APPROVE", "REJECT", "MODIFY", "REQUEST_MORE_INFORMATION", "ESCALATE")
_COMPLIANCE_OUTCOMES = ("CLEARED", "NOT_CLEARED", "REMEDIATION_REQUIRED")
_PERSONAS = ("CUSTOMER", "COLLECTIONS_OFFICER", "COLLECTIONS_MANAGER", "COMPLIANCE_RISK")


def upgrade() -> None:
    _create_escalation_case_table()
    _create_review_decision_table()
    _add_deferred_escalation_case_fks()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_decision")
    op.execute(
        "ALTER TABLE payment_arrangement "
        "DROP CONSTRAINT IF EXISTS fk_payment_arrangement_exception_case"
    )
    op.execute("ALTER TABLE proposal DROP CONSTRAINT IF EXISTS fk_proposal_case")
    op.execute("ALTER TABLE customer DROP CONSTRAINT IF EXISTS fk_customer_vulnerability_case")
    op.execute("DROP TABLE IF EXISTS escalation_case")


def _create_escalation_case_table() -> None:
    op.execute(
        create_table(
            "escalation_case",
            [
                id_column("case_id", "esc", primary_key=True),
                id_column("customer_id", "cus"),
                id_column("account_id", "acc"),
                id_column("conversation_id", "conv", nullable=True),
                id_column("item_id", "itm", nullable=True),
                enum_check_column("reason", _ESCALATION_REASONS, nullable=False),
                enum_check_column("queue", _REVIEW_QUEUES, nullable=False),
                enum_check_column("reviewer_role", _REVIEWER_ROLES, nullable=False),
                enum_check_column("priority", _ESCALATION_PRIORITIES, nullable=False),
                enum_check_column("status", _CASE_STATUSES, nullable=False),
                enum_check_column("source", _CASE_SOURCES, nullable=False),
                "summary varchar(500) NOT NULL",
                "requested_terms jsonb",
                "exception_types text[]",
                id_column("hardship_case_id", "hsp", nullable=True),
                id_column("dispute_id", "dsp", nullable=True),
                id_column("recommendation_id", "rec", nullable=True),
                id_column("parent_case_id", "esc", nullable=True),
                id_column("rerouted_to_case_id", "esc", nullable=True),
                policy_version_column("routing_policy_version"),
                "routing_flags text[] NOT NULL DEFAULT '{}'",
                timestamptz_column("first_reviewed_at", nullable=True),
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
                "FOREIGN KEY (item_id) REFERENCES delinquent_item (item_id)",
                "FOREIGN KEY (hardship_case_id) REFERENCES hardship_case (hardship_case_id)",
                "FOREIGN KEY (dispute_id) REFERENCES dispute (dispute_id)",
                "FOREIGN KEY (recommendation_id) REFERENCES recommendation (recommendation_id)",
                "FOREIGN KEY (parent_case_id) REFERENCES escalation_case (case_id) "
                "DEFERRABLE INITIALLY DEFERRED",
                "FOREIGN KEY (rerouted_to_case_id) REFERENCES escalation_case (case_id) "
                "DEFERRABLE INITIALLY DEFERRED",
                "CHECK ((status = 'RE_ROUTED') = (rerouted_to_case_id IS NOT NULL))",
                "CHECK (exception_types IS NULL OR exception_types <@ ARRAY['TERM','START_DATE',"
                "'AMOUNT_STRUCTURE']::text[])",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_escalation_case_queue_order ON escalation_case "
        "(queue, status, priority, created_at)"
    )
    op.execute("CREATE INDEX ix_escalation_case_customer_id ON escalation_case (customer_id)")
    op.execute(
        "CREATE INDEX ix_escalation_case_account_status ON escalation_case (account_id, status)"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_escalation_case_open_per_conversation_reason ON escalation_case "
        "(conversation_id, reason) WHERE status IN ('OPEN','IN_REVIEW','AWAITING_INFORMATION') "
        "AND conversation_id IS NOT NULL"
    )


def _create_review_decision_table() -> None:
    op.execute(
        create_table(
            "review_decision",
            [
                id_column("decision_id", "dec", primary_key=True),
                id_column("case_id", "esc"),
                enum_check_column("kind", _DECISION_KINDS, nullable=False),
                enum_check_column("action", _REVIEW_ACTIONS),
                enum_check_column("compliance_outcome", _COMPLIANCE_OUTCOMES),
                "reason varchar(1000)",
                "note varchar(1000)",
                "modification_option_id varchar(80)",
                enum_check_column("escalate_reason", _ESCALATION_REASONS),
                id_column("rerouted_case_id", "esc", nullable=True),
                "release_suppression boolean NOT NULL DEFAULT false",
                "overrode_ai boolean NOT NULL DEFAULT false",
                enum_check_column("reviewer_persona", _PERSONAS, nullable=False),
                timestamptz_column("decided_at", nullable=False),
                "case_version_after integer NOT NULL",
                policy_version_column(),
            ],
            extra=[
                "FOREIGN KEY (case_id) REFERENCES escalation_case (case_id) ON DELETE RESTRICT",
                "FOREIGN KEY (rerouted_case_id) REFERENCES escalation_case (case_id)",
                "CHECK (kind <> 'REVIEWER_ACTION' OR action IS NOT NULL)",
                "CHECK (kind <> 'COMPLIANCE_DECISION' "
                "OR (compliance_outcome IS NOT NULL AND reason IS NOT NULL))",
                "CHECK (action IS NULL OR action NOT IN ('REJECT','MODIFY','ESCALATE','APPROVE') "
                "OR reason IS NOT NULL)",
                "CHECK (action IS DISTINCT FROM 'REQUEST_MORE_INFORMATION' OR note IS NOT NULL)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_review_decision_case_decided ON review_decision (case_id, decided_at)"
    )
    op.execute(
        "CREATE INDEX ix_review_decision_overrode_ai ON review_decision (overrode_ai) "
        "WHERE overrode_ai"
    )


def _add_deferred_escalation_case_fks() -> None:
    op.execute(
        "ALTER TABLE hardship_case ADD CONSTRAINT fk_hardship_case_escalation_case "
        "FOREIGN KEY (escalation_case_id) REFERENCES escalation_case (case_id)"
    )
    op.execute(
        "ALTER TABLE dispute ADD CONSTRAINT fk_dispute_escalation_case "
        "FOREIGN KEY (escalation_case_id) REFERENCES escalation_case (case_id)"
    )
    op.execute(
        "ALTER TABLE customer ADD CONSTRAINT fk_customer_vulnerability_case "
        "FOREIGN KEY (vulnerability_case_id) REFERENCES escalation_case (case_id)"
    )
    op.execute(
        "ALTER TABLE proposal ADD CONSTRAINT fk_proposal_case "
        "FOREIGN KEY (case_id) REFERENCES escalation_case (case_id)"
    )
    op.execute(
        "ALTER TABLE payment_arrangement ADD CONSTRAINT fk_payment_arrangement_exception_case "
        "FOREIGN KEY (exception_case_id) REFERENCES escalation_case (case_id)"
    )
