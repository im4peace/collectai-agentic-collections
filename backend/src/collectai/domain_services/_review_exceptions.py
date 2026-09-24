"""Domain-layer exceptions for the review-decision workflow (E7-S2).

`domain_services` (layer 5a) may never import `api` (layer 7): every failure
mode `review_service.py` can raise is one of these small, framework-free
exceptions -- never one of `api.middleware.errors`'s HTTP-shaped exceptions.
`api/routers/escalations.py` catches each and translates it to the matching
HTTP status, mirroring `_ptp_exceptions.py`'s established split."""

from __future__ import annotations

from collectai.types.reason_codes import ReasonCode


class ReviewCaseNotFoundError(Exception):
    """No `escalation_case` exists for the given id (404)."""

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        super().__init__(f"No escalation case found for id {case_id!r}.")


class ReviewValidationError(Exception):
    """AC1/AC3/AC6: a structurally invalid decision body (422) -- a missing
    required field, or a `modification_option_id`/`escalate_reason` outside
    its deterministic eligible set."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class ReviewNotPermittedError(Exception):
    """AC5: `reviewer_persona` is not `COLLECTIONS_OFFICER`, or the case's
    own `reviewer_role` is not `COLLECTIONS_OFFICER` (object-level check:
    a COLLECTIONS_OFFICER may still not act on a COMPLIANCE_REVIEW-queue
    case). Mapped to 403."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class ReviewConflictError(Exception):
    """AC2/AC4/AC7/AC8: a 409 -- stale version, an already-decided/re-routed
    case, a policy-not-permitted case type, or an idempotency-key reused
    with different decision content."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)
