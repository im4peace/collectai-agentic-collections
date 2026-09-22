"""Data shapes returned by the arrangement eligibility service (E2-S3).

Mirrors api-contracts.md's `ScheduleEntry`, `ArrangementOption`,
`RequestedTerms` and `EligibilityResult`, with one local extension noted on
`EligibilityResult.permitted_paths`. Kept dependency-free (only `types.*`) so
both `_schedule.py` and `_classification.py` can import it without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from collectai.types.enums import EligibilityClass, ExceptionType
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    """One installment due date and amount (api-contracts.md `ScheduleEntry`)."""

    sequence: int
    due_date: date
    amount: Money


@dataclass(frozen=True, slots=True)
class ArrangementOption:
    """One eligible installment option (api-contracts.md `ArrangementOption`)."""

    option_id: str
    installment_count: int
    installment_amount: Money
    final_installment_amount: Money
    total_amount: Money
    first_installment_date: date
    frequency: str
    schedule: list[ScheduleEntry]


@dataclass(frozen=True, slots=True)
class RequestedTerms:
    """Customer-requested arrangement terms (api-contracts.md `RequestedTerms`)."""

    installment_count: int
    first_installment_date: date
    installment_amount: Money | None


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """Deterministic eligibility outcome (api-contracts.md `EligibilityResult`).

    `permitted_paths` is a local extension (not in the API contract's
    `EligibilityResult` shape): when `reason_code` is `CONFLICTING_ACTIVE_ITEM`
    (AC4), it names the actions still open to the customer/officer, e.g.
    `["AMEND", "CANCEL"]` on the conflicting PTP or arrangement. Empty
    otherwise. A later story maps this onto whatever UI affordance it needs.
    """

    classification: EligibilityClass
    reason_code: ReasonCode | None
    options: list[ArrangementOption]
    requested_terms: RequestedTerms | None
    exception_types: list[ExceptionType]
    within_reviewer_thresholds: bool | None
    permitted_paths: list[str] = field(default_factory=list)
