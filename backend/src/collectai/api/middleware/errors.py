"""Correlation-id propagation and the error envelope (E3-S1;
api-contracts.md 1.2, 1.3).

Two responsibilities live here because they are two sides of the same
contract: `X-Correlation-Id` must be on every response (success or error),
and every non-2xx response must have the exact `ErrorEnvelope` shape. Wiring
both from `api/app.py` in one place keeps that contract in one file instead
of scattered across every router.

NOTE: this file is past the code-gen skill's 200-line warning threshold
(still well under the 300-line block threshold). If a future story adds
another business-specific exception/handler pair here, split the envelope
models (`ErrorDetail`, `ErrorBody`, `ErrorEnvelope`) into their own
`api/schemas/errors.py` first, since that is the natural seam.
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
from pydantic import BaseModel, ConfigDict

from collectai.api.rbac import ForbiddenError, UnauthenticatedError
from collectai.types.enums import ErrorCode
from collectai.types.reason_codes import ReasonCode

logger = logging.getLogger(__name__)

_CORRELATION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ErrorDetail(BaseModel):
    """One field-level violation inside `ErrorEnvelope.error.details`."""

    model_config = ConfigDict(frozen=True)

    field: str | None = None
    reason_code: str
    message: str


class ErrorBody(BaseModel):
    """The `error` object of `ErrorEnvelope` (api-contracts.md 1.3)."""

    model_config = ConfigDict(frozen=True)

    code: str
    reason_code: str | None = None
    message: str
    correlation_id: str
    policy_version: str | None = None
    details: list[ErrorDetail] = []
    alternatives: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    """Every non-2xx response has this shape (api-contracts.md 1.3)."""

    model_config = ConfigDict(frozen=True)

    error: ErrorBody


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
    (e.g. api-contracts.md's `CUSTOMER_ID_REQUIRED_OR_FORBIDDEN`). Mapped to
    422 `VALIDATION_ERROR` with the given `reason_code`."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


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
    """Map every error this layer knows about to the `ErrorEnvelope` shape.
    Business-rule-specific codes (BUSINESS_RULE_VIOLATION, CONFLICT, ...)
    are added by the stories that introduce those rules; this registers
    only the auth and generic-failure handlers E3-S1 owns."""
    app.add_exception_handler(UnauthenticatedError, _handle_unauthenticated)
    app.add_exception_handler(ForbiddenError, _handle_forbidden)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(NotFoundError, _handle_not_found)
    app.add_exception_handler(RequestValidationFailedError, _handle_request_validation_failed)
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
) -> JSONResponse:
    correlation_id = resolve_correlation_id(request)
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code.value,
            reason_code=reason_code.value if reason_code else None,
            message=message,
            correlation_id=correlation_id,
            details=details or [],
        )
    )
    response = JSONResponse(status_code=http_status, content=body.model_dump())
    response.headers["X-Correlation-Id"] = correlation_id
    return response
