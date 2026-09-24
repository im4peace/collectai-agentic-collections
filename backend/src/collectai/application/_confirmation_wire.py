"""JSON-safe wire-dict construction for `confirmation_flow.py`'s
`ConfirmResult` idempotency-stored response body, split out to keep that
module under the code-gen skill's 300-line block threshold. Pure functions
only: no session, no I/O.
"""

from __future__ import annotations

import hashlib
from typing import Any

from collectai.domain_services import proposal_service
from collectai.persistence.orm.chat_message import ChatMessageOrm
from collectai.persistence.orm.proposal import ProposalOrm


def hash_confirm_request(*, proposal_id: str, terms_hash: str) -> str:
    """Deterministic hash of the confirm request's identifying fields, used
    to detect `IDEMPOTENCY_KEY_REUSED` (the same key sent with a different
    `(proposal_id, terms_hash)`) independently of
    `domain_services.idempotency.IdempotencyService`, which never compares
    `request_hash` itself."""
    canonical = f"{proposal_id}:{terms_hash}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def message_wire_dict(row: ChatMessageOrm) -> dict[str, Any]:
    return {
        "message_id": row.message_id,
        "conversation_id": row.conversation_id,
        "role": row.role,
        "content": row.content,
        "content_source": row.content_source,
        "labels": list(row.labels),
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }


def build_confirm_response_body(
    *,
    proposal: ProposalOrm,
    outcome_kind: str,
    ptp_wire: dict[str, object] | None,
    payment_wire: dict[str, object] | None,
    message_wire: dict[str, Any],
) -> dict[str, Any]:
    return {
        "proposal": proposal_service.to_wire(proposal),
        "outcome": {
            "kind": outcome_kind,
            "ptp": ptp_wire,
            "payment_event": payment_wire,
            "arrangement": None,
            "escalation": None,
        },
        "assistant_message": message_wire,
    }
