"""Domain-layer exceptions for the demo-controls workflow (E9-S3).

Mirrors `_review_exceptions.py`'s established split: `domain_services`
(layer 5a) never imports `api` (layer 7), so `api/routers/demo_controls.py`
catches each of these and translates it to the matching HTTP status."""

from __future__ import annotations

from collectai.types.reason_codes import ReasonCode


class DemoAccountNotFoundError(Exception):
    """No account (or its delinquency record) exists for the given id (404)."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"No account found for id {account_id!r}.")


class DemoValidationError(Exception):
    """A deterministic amount rule rejected the simulated payment (422
    `BUSINESS_RULE_VIOLATION`)."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)
