"""Correlation-id propagation and the error envelope (E3-S1; extended by
Group E's API stories: E3-S2, E3-S5, E4-S1, E6-S6, E9-S1).

Two responsibilities live here because they are two sides of the same
contract: `X-Correlation-Id` must be on every response (success or error),
and every non-2xx response must have the exact `ErrorEnvelope` shape. Wiring
both from `api/app.py` in one place keeps that contract in one file instead
of scattered across every router. The `ErrorEnvelope`/`ErrorBody`/
`ErrorDetail` Pydantic models themselves live in `api/schemas/errors.py` (see
that module's docstring) so this file only holds exceptions, handlers and the
correlation-id middleware.

Business-rule-specific reason codes are supplied by the raising router/
service (a `ReasonCode` member), not hard-coded per exception class: every
Group E story that rejects a request for a deterministic business reason
raises one of `BusinessRuleViolationError` (422) or `ConflictError` (409)
with its own `reason_code` rather than adding a new exception class per rule.
The exception classes themselves live in `api/middleware/error_types.py`
(split out once this module crossed the 300-line block threshold); this
module re-exports every one of them so existing `from
collectai.api.middleware.errors import NotFoundError`-style imports keep
working unchanged.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Final

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from collectai.api.middleware.error_types import (
    AuditUnavailableError,
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
    PolicyUnavailableError,
    RateLimitedError,
    RequestValidationFailedError,
)
from collectai.api.rbac import ForbiddenError, UnauthenticatedError
from collectai.api.schemas.errors import ErrorBody, ErrorDetail, ErrorEnvelope
from collectai.types.enums import ErrorCode
from collectai.types.reason_codes import ReasonCode

logger = logging.getLogger(__name__)

_CORRELATION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

__all__ = [
    "AuditUnavailableError",
    "BusinessRuleViolationError",
    "ConflictError",
    "ErrorBody",
    "ErrorDetail",
    "ErrorEnvelope",
    "NotFoundError",
    "PolicyUnavailableError",
    "RateLimitedError",
    "RequestValidationFailedError",
    "build_error_response",
    "correlation_id_middleware",
    "register_error_handlers",
    "resolve_correlation_id",
]


def resolve_correlation_id(request: Request) -> str:
    """The correlation id the correlation-id middleware attached to
    `request.state` (api-contracts.md: "Propagated to audit events, logs
    and provider calls"). Generates one defensively if a caller resolves it
    before the middleware has run (e.g. a dependency exercised directly in
    a unit test), so this never raises."""
    existing = getattr(request.state, "correlation_id", None)
    if isinstance(existing, str) and existing:
        return existing
    return _generate_correlation_id()


async def correlation_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    """ASGI middleware: validate/generate `X-Correlation-Id`, store it on
    `request.state` for dependencies and handlers to read, and always
    return it on the response (api-contracts.md 1.2)."""
    inbound = request.headers.get("X-Correlation-Id")
    is_valid_inbound = inbound is not None and _CORRELATION_ID_PATTERN.match(inbound) is not None
    correlation_id = inbound if is_valid_inbound and inbound else _generate_correlation_id()
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


def _generate_correlation_id() -> str:
    return uuid.uuid4().hex


def register_error_handlers(app: FastAPI) -> None:
    """Map every error this layer knows about to the `ErrorEnvelope` shape."""
    app.add_exception_handler(UnauthenticatedError, _handle_unauthenticated)
    app.add_exception_handler(ForbiddenError, _handle_forbidden)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(NotFoundError, _handle_not_found)
    app.add_exception_handler(RequestValidationFailedError, _handle_request_validation_failed)
    app.add_exception_handler(BusinessRuleViolationError, _handle_business_rule_violation)
    app.add_exception_handler(ConflictError, _handle_conflict)
    app.add_exception_handler(RateLimitedError, _handle_rate_limited)
    app.add_exception_handler(PolicyUnavailableError, _handle_policy_unavailable)
    app.add_exception_handler(AuditUnavailableError, _handle_audit_unavailable)
    app.add_exception_handler(Exception, _handle_unexpected_error)


async def _handle_unauthenticated(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, UnauthenticatedError)  # noqa: S101 - handler is type-bound
    return build_error_response(
        request, status.HTTP_401_UNAUTHORIZED, ErrorCode.UNAUTHENTICATED, message=exc.reason
    )


async def _handle_forbidden(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ForbiddenError)  # noqa: S101 - handler is type-bound by registration
    return build_error_response(
        request, status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, message=str(exc)
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - handler is type-bound
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"] if part != "body") or None,
            reason_code=ReasonCode.FIELD_INVALID.value,
            message=error["msg"],
        )
        for error in exc.errors()
    ]
    return build_error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_ERROR,
        message="Request validation failed.",
        reason_code=ReasonCode.FIELD_INVALID,
        details=details,
    )


async def _handle_not_found(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, NotFoundError)  # noqa: S101 - handler is type-bound by registration
    return build_error_response(
        request, status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, message=exc.message
    )


async def _handle_request_validation_failed(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationFailedError)  # noqa: S101 - type-bound by registration
    return build_error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_ERROR,
        message=exc.message,
        reason_code=exc.reason_code,
    )


async def _handle_business_rule_violation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BusinessRuleViolationError)  # noqa: S101 - type-bound by registration
    return build_error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.BUSINESS_RULE_VIOLATION,
        message=exc.message,
        reason_code=exc.reason_code,
        details=exc.details,
        alternatives=exc.alternatives,
    )


async def _handle_conflict(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ConflictError)  # noqa: S101 - handler is type-bound by registration
    return build_error_response(
        request,
        status.HTTP_409_CONFLICT,
        ErrorCode.CONFLICT,
        message=exc.message,
        reason_code=exc.reason_code,
        context=exc.context,
    )


async def _handle_rate_limited(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitedError)  # noqa: S101 - handler is type-bound by registration
    response = build_error_response(
        request, status.HTTP_429_TOO_MANY_REQUESTS, ErrorCode.RATE_LIMITED, message=exc.message
    )
    response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response


async def _handle_policy_unavailable(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PolicyUnavailableError)  # noqa: S101 - type-bound by registration
    return build_error_response(
        request,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.POLICY_UNAVAILABLE,
        message=exc.message,
        reason_code=ReasonCode.POLICY_UNAVAILABLE,
    )


async def _handle_audit_unavailable(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AuditUnavailableError)  # noqa: S101 - type-bound by registration
    return build_error_response(
        request,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.AUDIT_UNAVAILABLE,
        message=exc.message,
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = resolve_correlation_id(request)
    logger.error(
        "Unhandled exception",
        extra={"correlation_id": correlation_id, "path": request.url.path},
        exc_info=exc,
    )
    return build_error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        message="An internal error occurred.",
    )


def build_error_response(
    request: Request,
    http_status: int,
    code: ErrorCode,
    *,
    message: str,
    reason_code: ReasonCode | None = None,
    details: list[ErrorDetail] | None = None,
    alternatives: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    policy_version: str | None = None,
) -> JSONResponse:
    correlation_id = resolve_correlation_id(request)
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code.value,
            reason_code=reason_code.value if reason_code else None,
            message=message,
            correlation_id=correlation_id,
            policy_version=policy_version,
            details=details or [],
            alternatives=alternatives,
            context=context,
        )
    )
    response = JSONResponse(status_code=http_status, content=body.model_dump())
    response.headers["X-Correlation-Id"] = correlation_id
    return response
