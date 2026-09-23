"""The `ErrorEnvelope` wire shape (api-contracts.md 1.3), split out of
`api/middleware/errors.py` per that module's own note: these are pure
Pydantic response models with no framework or exception-handling logic, and
splitting them here keeps `middleware/errors.py` under the code-gen skill's
300-line block threshold as Group E's stories add their own typed exceptions
and handlers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


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
