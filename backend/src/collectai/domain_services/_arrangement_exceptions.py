"""Domain-layer exceptions for `arrangement_service.py` (E8-S1, extended by
E8-S3 AC3), mirroring `_ptp_exceptions.py`'s split: `domain_services`
(layer 5a) may never import `application` (layer 6) or `api` (layer 7), so
`_confirmation_apply.py` catches these and translates them to its own
`ProposalInvalidError`/`ProposalConflictError`, the same way it already
does for `_ptp_exceptions.PtpBusinessRuleViolation`/`PtpConflictError`."""

from __future__ import annotations

from collectai.types.reason_codes import ReasonCode


class ArrangementNotEligibleError(Exception):
    """E8-S1 AC3: at confirm time, a fresh `get_eligible_options()` re-run
    found the account no longer eligible at all (state changed since the
    offer), or the offered `option_id` is no longer among the current
    options."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ArrangementConflictError(Exception):
    """E8-S3 AC3: `DISPUTED_ITEM` -- an open dispute on the account blocks
    arrangement creation until a human resolves it."""

    def __init__(self, *, reason_code: ReasonCode, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)
