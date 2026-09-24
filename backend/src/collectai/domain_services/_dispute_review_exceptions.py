"""Domain-layer exceptions for the dispute review/resolve workflow (E8-S4).

Mirrors `_review_exceptions.py`'s established split: `domain_services`
(layer 5a) never imports `api` (layer 7), so every failure mode
`dispute_review_service.py` can raise is one of these small, framework-free
exceptions -- `api/routers/disputes.py` catches each and translates it to
the matching HTTP status."""

from __future__ import annotations

from collectai.types.reason_codes import ReasonCode


class DisputeNotFoundError(Exception):
    """No `dispute` exists for the given id (404)."""

    def __init__(self, dispute_id: str) -> None:
        self.dispute_id = dispute_id
        super().__init__(f"No dispute found for id {dispute_id!r}.")


class DisputeValidationError(Exception):
    """AC1: a structurally invalid resolve body (422) -- missing outcome or
    empty reason."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class DisputeNotPermittedError(Exception):
    """AC4: `reviewer_persona` is not `COLLECTIONS_OFFICER`. Mapped to 403."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class DisputeConflictError(Exception):
    """AC2/AC5: a 409 -- stale version, a transition outside OPEN ->
    UNDER_REVIEW -> RESOLVED, or an idempotency key reused with different
    content."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)
