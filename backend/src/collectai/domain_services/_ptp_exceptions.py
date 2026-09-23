"""Domain-layer exceptions for the Promise-to-Pay workflow (E6-S6).

`domain_services` (layer 5a, folder-structure.md section 5) may never import
`api` (layer 7), so every failure mode `ptp_service.py` can raise is a small,
framework-free exception defined here -- never one of `api.middleware.errors`'s
HTTP-shaped exceptions. `api/routers/ptps.py` catches each of these and
translates it to the matching HTTP error.

Split out of `ptp_service.py` so both `_ptp_idempotency.py` and
`ptp_service.py` can raise `PtpConflictError` without an import cycle between
them (`ptp_service.py` orchestrates; `_ptp_idempotency.py` is one of the
things it orchestrates).
"""

from __future__ import annotations

from typing import Any

from collectai.types.reason_codes import ReasonCode


class PtpAccountNotFoundError(Exception):
    """No `delinquency_record` exists for the given account (404, unknown
    account -- api-contracts.md's identical-body-for-both-cases 404)."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"No delinquency record found for account {account_id!r}.")


class PtpBusinessRuleViolation(Exception):
    """`rules_engine.ptp_rules.validate_ptp` rejected the amount or date."""

    def __init__(
        self, *, reason_code: ReasonCode, message: str, alternatives: dict[str, Any] | None
    ) -> None:
        self.reason_code = reason_code
        self.message = message
        self.alternatives = alternatives
        super().__init__(message)


class PtpConflictError(Exception):
    """A state/staleness/duplicate conflict: `CONFLICTING_ACTIVE_ITEM`,
    `DISPUTED_ITEM`, `STALE_DATA`, `AMBIGUOUS_VALIDATION` or
    `IDEMPOTENCY_KEY_REUSED`."""

    def __init__(
        self, *, reason_code: ReasonCode, message: str, context: dict[str, Any] | None = None
    ) -> None:
        self.reason_code = reason_code
        self.message = message
        self.context = context
        super().__init__(message)
