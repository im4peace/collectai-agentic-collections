"""Typed API-layer exceptions mapped to the `ErrorEnvelope` shape
(api-contracts.md 1.3), split out of `api/middleware/errors.py` once that
module crossed the code-gen skill's 300-line block threshold (principle #1).
`errors.py` re-exports every name here, registers a handler per class and
owns `build_error_response`; this module only defines the exceptions
themselves, with no FastAPI/handler logic, so any layer may raise one
without importing FastAPI.

Business-rule-specific reason codes are supplied by the raising router/
service (a `ReasonCode` member), not hard-coded per exception class: every
Group E story that rejects a request for a deterministic business reason
raises one of `BusinessRuleViolationError` (422) or `ConflictError` (409)
with its own `reason_code` rather than adding a new exception class per rule.
"""

from __future__ import annotations

from typing import Any

from collectai.api.schemas.errors import ErrorDetail
from collectai.types.reason_codes import ReasonCode


class NotFoundError(Exception):
    """A referenced resource does not exist (or, for a cross-customer
    lookup, is indistinguishable from not existing). Mapped to 404
    `NOT_FOUND`. Generic and reusable: any router may raise this rather
    than building its own 404 envelope by hand."""

    def __init__(self, *, message: str) -> None:
        self.message = message
        super().__init__(message)


class RequestValidationFailedError(Exception):
    """A business-shape validation rule the request body violates, distinct
    from FastAPI/Pydantic's own field-shape `RequestValidationError`
    (e.g. api-contracts.md's `CUSTOMER_ID_REQUIRED_OR_FORBIDDEN`,
    `FILTER_REQUIRED`, `IDEMPOTENCY_KEY_REQUIRED`). Mapped to 422
    `VALIDATION_ERROR` with the given `reason_code`."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class BusinessRuleViolationError(Exception):
    """A deterministic rule rejected the request (api-contracts.md 1.3).
    Mapped to 422 `BUSINESS_RULE_VIOLATION`. `alternatives` carries the
    envelope's `alternatives` block (e.g. a valid amount/date range);
    `details` carries per-field violations when more than one rule failed."""

    def __init__(
        self,
        *,
        reason_code: ReasonCode,
        message: str,
        details: list[ErrorDetail] | None = None,
        alternatives: dict[str, Any] | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.message = message
        self.details = details or []
        self.alternatives = alternatives
        super().__init__(message)


class ConflictError(Exception):
    """A state, version, staleness or duplicate-request conflict
    (api-contracts.md 1.3: `CONFLICTING_ACTIVE_ITEM`, `DISPUTED_ITEM`,
    `STALE_DATA`, `VERSION_CONFLICT`, `INVALID_STATE_TRANSITION`,
    `IDEMPOTENCY_KEY_REUSED`, ...). Mapped to 409 `CONFLICT`. `context`
    carries envelope-specific detail such as `permitted_paths` or
    `refreshed_context`."""

    def __init__(
        self, *, reason_code: ReasonCode, message: str, context: dict[str, Any] | None = None
    ) -> None:
        self.reason_code = reason_code
        self.message = message
        self.context = context
        super().__init__(message)


class PolicyUnavailableError(Exception):
    """No valid active `PolicyRuleSet`: fail closed (specs/policy-ruleset
    -contract.md section 1). Mapped to 503 `POLICY_UNAVAILABLE`."""

    def __init__(
        self, *, message: str = "No valid active PolicyRuleSet is available."
    ) -> None:
        self.message = message
        super().__init__(message)


class RateLimitedError(Exception):
    """More than the configured requests-per-minute from the same session
    (E6-S1 AC6; api-contracts.md 1.2's in-process sliding window). Mapped to
    429 `RATE_LIMITED` with a `Retry-After` header carrying
    `retry_after_seconds`."""

    def __init__(
        self, *, retry_after_seconds: int, message: str = "Rate limit exceeded."
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.message = message
        super().__init__(message)


class AuditUnavailableError(Exception):
    """The audit write for a state transition failed; the transaction was
    rolled back and the transition never happened (E1-S4 AC5). Mapped to 503
    `AUDIT_UNAVAILABLE`. Routers raise this from `audit.service.AuditUnavailable`
    inside their own `except` block rather than letting the domain-layer
    exception leak past the API boundary unmapped."""

    def __init__(
        self, *, message: str = "Audit event could not be persisted; the write was rolled back."
    ) -> None:
        self.message = message
        super().__init__(message)


class ObjectForbiddenError(Exception):
    """An authenticated, capability-holding caller may not act on this
    specific resource (E7-S2 AC5: a case whose own `reviewer_role` does not
    match the caller, even though the caller's persona generally holds the
    endpoint's capability). Mapped to 403 `FORBIDDEN` with the given
    `reason_code` -- distinct from `rbac.ForbiddenError`'s persona-level
    check, the object-level counterpart to how `QueueNotPermittedError`
    covers one specific case of this same family."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class QueueNotPermittedError(Exception):
    """E7-S1 AC7/api-contracts.md 3.9: `COMPLIANCE_RISK` requested a queue
    other than `COMPLIANCE_REVIEW` on `GET /api/escalations`. Mapped to 403
    `FORBIDDEN` with `reason_code` `QUEUE_NOT_PERMITTED` -- distinct from
    `rbac.ForbiddenError` (a capability-level denial with no reason code):
    this is an authenticated, capability-holding caller asking for a scope
    their role does not cover."""

    def __init__(
        self, *, message: str = "COMPLIANCE_RISK may only view the COMPLIANCE_REVIEW queue."
    ) -> None:
        self.message = message
        super().__init__(message)


class HandoffFailedError(Exception):
    """`POST /api/chat/conversations/{conversation_id}/handoff` could not
    create the escalation case (E7-S1 AC4, api-contracts.md 3.8's handoff
    behaviour note). Mapped to 503 `HANDOFF_FAILED`, distinct from the
    generic `AuditUnavailableError` so the customer-facing next step stays
    specific to "the handoff was not completed" rather than a generic audit
    failure message."""

    def __init__(
        self, *, message: str = "The handoff could not be completed. Please try again shortly."
    ) -> None:
        self.message = message
        super().__init__(message)
