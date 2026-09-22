"""conversation, chat_message, proposal, chat_turn, recommendation

Revision ID: 0002_conversation_chat
Revises: 0001_customer_account_delinquency
Create Date: 2026-09-22

NOTE: nearing the 300-line block threshold. `chat_message` and `chat_turn`
reference each other (turn_id / customer_message_id, assistant_message_id),
so `chat_message.turn_id`'s FK is added via ALTER TABLE after `chat_turn`
exists, rather than inline — see `_add_chat_message_turn_fk`.
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

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_CONVERSATION_STATUSES = ("ACTIVE", "HANDED_OFF", "CLOSED")
_MESSAGE_ROLES = ("CUSTOMER", "ASSISTANT", "SYSTEM")
_CONTENT_SOURCES = ("CUSTOMER_INPUT", "MODEL", "TEMPLATE")
_SAFE_STATES = (
    "NONE",
    "AI_UNAVAILABLE",
    "HANDOFF_CREATED",
    "HANDOFF_FAILED",
    "POLICY_UNAVAILABLE",
    "AUDIT_UNAVAILABLE",
    "TOOL_CAP_REACHED",
    "STALE_DATA_REFRESHED",
)
_PROPOSAL_KINDS = ("PTP", "PAYMENT", "ARRANGEMENT", "EXCEPTION_REQUEST")
_PROPOSAL_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "CANCELLED", "EXPIRED", "INVALIDATED")
_NBA_ACTIONS = (
    "CONTACT_CUSTOMER",
    "REQUEST_PAYMENT",
    "OFFER_ELIGIBLE_ARRANGEMENT",
    "FOLLOW_UP_PTP",
    "REFER_TO_HARDSHIP_WORKFLOW",
    "ESCALATE_TO_HUMAN_REVIEW",
)
_RECOMMENDATION_STATUSES = ("GENERATED", "SAFE_FALLBACK", "HUMAN_REVIEW_ONLY")
_CONTENT_SOURCES_MODEL_TEMPLATE = ("MODEL", "TEMPLATE")
_RECOMMENDATION_DECISIONS = ("ACCEPTED", "OVERRIDDEN")


def upgrade() -> None:
    _create_conversation_table()
    _create_chat_message_table()
    _create_proposal_table()
    _create_chat_turn_table()
    _add_chat_message_turn_fk()
    _add_interaction_conversation_fk()
    _create_recommendation_table()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendation")
    op.execute("ALTER TABLE interaction DROP CONSTRAINT IF EXISTS fk_interaction_conversation")
    op.execute("DROP TABLE IF EXISTS chat_turn")
    op.execute("DROP TABLE IF EXISTS proposal")
    op.execute("DROP TABLE IF EXISTS chat_message")
    op.execute("DROP TABLE IF EXISTS conversation")


def _create_conversation_table() -> None:
    op.execute(
        create_table(
            "conversation",
            [
                id_column("conversation_id", "conv", primary_key=True),
                id_column("customer_id", "cus"),
                id_column("account_id", "acc"),
                enum_check_column("status", _CONVERSATION_STATUSES, nullable=False),
                "clarification_count integer NOT NULL DEFAULT 0",
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("last_message_at", nullable=True),
            ],
            extra=[
                "FOREIGN KEY (account_id, customer_id) "
                "REFERENCES account (account_id, customer_id)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_conversation_customer_created "
        "ON conversation (customer_id, created_at DESC)"
    )
    op.execute("CREATE INDEX ix_conversation_account_id ON conversation (account_id)")


def _create_chat_message_table() -> None:
    # turn_id's FK to chat_turn is added by _add_chat_message_turn_fk once
    # chat_turn exists (chat_message and chat_turn reference each other).
    op.execute(
        create_table(
            "chat_message",
            [
                id_column("message_id", "msg", primary_key=True),
                id_column("conversation_id", "conv"),
                id_column("customer_id", "cus"),
                id_column("turn_id", "trn", nullable=True),
                enum_check_column("role", _MESSAGE_ROLES, nullable=False),
                "content varchar(2000) NOT NULL",
                enum_check_column("content_source", _CONTENT_SOURCES, nullable=False),
                "labels text[] NOT NULL DEFAULT '{}'",
                timestamptz_column("created_at", nullable=False),
            ],
            extra=[
                "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id) "
                "ON DELETE CASCADE",
                "CHECK ((role = 'CUSTOMER') = (content_source = 'CUSTOMER_INPUT'))",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_chat_message_conversation_created "
        "ON chat_message (conversation_id, created_at)"
    )
    op.execute("CREATE INDEX ix_chat_message_customer_id ON chat_message (customer_id)")


def _create_proposal_table() -> None:
    # case_id's FK to escalation_case is added by migration 0004 once
    # escalation_case exists.
    op.execute(
        create_table(
            "proposal",
            [
                id_column("proposal_id", "prp", primary_key=True),
                id_column("conversation_id", "conv", nullable=True),
                id_column("case_id", "esc", nullable=True),
                id_column("customer_id", "cus"),
                id_column("account_id", "acc"),
                enum_check_column("kind", _PROPOSAL_KINDS, nullable=False),
                enum_check_column("status", _PROPOSAL_STATUSES, nullable=False),
                "terms jsonb NOT NULL",
                "terms_hash char(64) NOT NULL",
                "summary varchar(500) NOT NULL",
                "simulated boolean NOT NULL",
                "record_version integer NOT NULL",
                "policy_version varchar(40) NOT NULL",
                timestamptz_column("created_at", nullable=False),
                timestamptz_column("expires_at", nullable=False),
                timestamptz_column("confirmed_at", nullable=True),
                "resulting_resource_id text",
            ],
            extra=[
                "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id) "
                "ON DELETE CASCADE",
                "CHECK (kind <> 'PAYMENT' OR simulated)",
                "CHECK ((status = 'CONFIRMED') = (confirmed_at IS NOT NULL))",
            ],
        )
    )
    op.execute("CREATE INDEX ix_proposal_conversation_status ON proposal (conversation_id, status)")
    op.execute(
        "CREATE UNIQUE INDEX ux_proposal_pending_per_conversation ON proposal (conversation_id) "
        "WHERE status = 'PENDING_CONFIRMATION'"
    )
    op.execute("CREATE INDEX ix_proposal_customer_id ON proposal (customer_id)")


def _create_chat_turn_table() -> None:
    op.execute(
        create_table(
            "chat_turn",
            [
                id_column("turn_id", "trn", primary_key=True),
                id_column("conversation_id", "conv"),
                id_column("customer_id", "cus"),
                id_column("customer_message_id", "msg"),
                id_column("assistant_message_id", "msg"),
                "intent jsonb",
                id_column("proposal_id", "prp", nullable=True),
                enum_check_column("safe_state", _SAFE_STATES, nullable=False),
                "correlation_id varchar(64) NOT NULL",
                "tool_call_count integer NOT NULL",
                timestamptz_column("created_at", nullable=False),
            ],
            extra=[
                "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id) "
                "ON DELETE CASCADE",
                "FOREIGN KEY (customer_message_id) REFERENCES chat_message (message_id)",
                "FOREIGN KEY (assistant_message_id) REFERENCES chat_message (message_id)",
                "FOREIGN KEY (proposal_id) REFERENCES proposal (proposal_id)",
                "CHECK (tool_call_count >= 0)",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_chat_turn_conversation_created ON chat_turn (conversation_id, created_at)"
    )
    op.execute("CREATE INDEX ix_chat_turn_correlation_id ON chat_turn (correlation_id)")


def _add_chat_message_turn_fk() -> None:
    op.execute(
        "ALTER TABLE chat_message ADD CONSTRAINT fk_chat_message_turn "
        "FOREIGN KEY (turn_id) REFERENCES chat_turn (turn_id)"
    )


def _add_interaction_conversation_fk() -> None:
    op.execute(
        "ALTER TABLE interaction ADD CONSTRAINT fk_interaction_conversation "
        "FOREIGN KEY (conversation_id) REFERENCES conversation (conversation_id)"
    )


def _create_recommendation_table() -> None:
    # audit_event_id deliberately has no FK: audit_event is created by E1-S4
    # and, per data-models.md section 4.1, is never an FK target so audit
    # rows survive reseed.
    op.execute(
        create_table(
            "recommendation",
            [
                id_column("recommendation_id", "rec", primary_key=True),
                id_column("account_id", "acc"),
                id_column("customer_id", "cus"),
                enum_check_column("action", _NBA_ACTIONS, nullable=False),
                "rationale varchar(1500) NOT NULL",
                "referenced_factor_ids text[] NOT NULL DEFAULT '{}'",
                enum_check_column("status", _RECOMMENDATION_STATUSES, nullable=False),
                enum_check_column(
                    "content_source", _CONTENT_SOURCES_MODEL_TEMPLATE, nullable=False
                ),
                "model_id varchar(120)",
                "prompt_version varchar(40)",
                "policy_version varchar(40) NOT NULL",
                "record_version integer NOT NULL",
                "correlation_id varchar(64) NOT NULL",
                timestamptz_column("created_at", nullable=False),
                id_column("audit_event_id", "aud"),
                enum_check_column("officer_decision", _RECOMMENDATION_DECISIONS),
                "officer_decision_reason varchar(1000)",
                enum_check_column("officer_chosen_action", _NBA_ACTIONS),
                "decided_by_persona text",
                timestamptz_column("decided_at", nullable=True),
            ],
            extra=[
                "FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE CASCADE",
                "CHECK (officer_decision IS DISTINCT FROM 'OVERRIDDEN' "
                "OR officer_decision_reason IS NOT NULL)",
                "CHECK (status <> 'HUMAN_REVIEW_ONLY' OR action = 'ESCALATE_TO_HUMAN_REVIEW')",
                "CHECK (content_source = 'TEMPLATE' "
                "OR (model_id IS NOT NULL AND prompt_version IS NOT NULL))",
            ],
        )
    )
    op.execute(
        "CREATE INDEX ix_recommendation_account_created "
        "ON recommendation (account_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_recommendation_officer_decision ON recommendation (officer_decision) "
        "WHERE officer_decision IS NOT NULL"
    )
