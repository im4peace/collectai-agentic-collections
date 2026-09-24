"""Domain-layer exceptions for `confirmation_flow.py` (E6-S2, E6-S3),
mirroring `domain_services._ptp_exceptions.py`'s pattern: `application` may
import `api` in principle, but these stay framework-free so
`api/routers/chat_proposals.py` alone decides the HTTP status/envelope,
exactly as `api/routers/ptps.py` does for `domain_services._ptp_exceptions`.
"""

from __future__ import annotations

from typing import Any

from collectai.types.reason_codes import ReasonCode


class ProposalNotFoundError(Exception):
    """No proposal with this id exists for this conversation/customer (404,
    identical body to a cross-customer attempt)."""

    def __init__(self, proposal_id: str) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"No proposal {proposal_id!r} found for this conversation.")


class ProposalInvalidError(Exception):
    """409 `PROPOSAL_INVALID`: stale record_version, altered terms_hash,
    expired, already cancelled/confirmed, or no longer authorized."""

    def __init__(self, *, message: str, context: dict[str, Any] | None = None) -> None:
        self.message = message
        self.context = context
        super().__init__(message)


class ProposalConflictError(Exception):
    """409 `CONFLICTING_ACTIVE_ITEM` / `DISPUTED_ITEM`."""

    def __init__(
        self, *, reason_code: ReasonCode, message: str, context: dict[str, Any] | None = None
    ) -> None:
        self.reason_code = reason_code
        self.message = message
        self.context = context
        super().__init__(message)


class ProposalAmbiguousValidationError(Exception):
    """409 `AMBIGUOUS_VALIDATION`: freshness could not be established.
    `escalation_case_id` is always set -- `confirm_proposal` creates the
    escalation before raising this."""

    def __init__(self, *, escalation_case_id: str) -> None:
        self.escalation_case_id = escalation_case_id
        super().__init__("Freshness could not be established; a specialist has been notified.")


class ConfirmIdempotencyReuseError(Exception):
    """409 `IDEMPOTENCY_KEY_REUSED`: the same `Idempotency-Key` was sent
    with a different `(proposal_id, terms_hash)`."""

    def __init__(self) -> None:
        super().__init__("This Idempotency-Key was already used with a different request body.")
