"""Contract validation for `PolicyParameters` (specs/policy-ruleset-contract.md).

`validate_policy_parameters` is the single entry point: it parses raw
(already-JSON-decoded) data through the structural `PolicyParameters` model
and then applies every cross-field / cross-section rule the contract defines
that Pydantic field constraints cannot express declaratively (band-cutoff
ordering, routing-table completeness, cross-section thresholds, ...).

Every failure — structural or cross-field — surfaces as a `PolicyValidationError`
naming the offending parameter, per AC2 ("the application fails to start with
a named error identifying the parameter"). Never partially applied: the first
failure found aborts validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from collectai.config.policy.models import PolicyParameters
from collectai.types.enums import (
    ContactOutcome,
    EscalationPriority,
    EscalationReason,
    ReviewerRole,
    ReviewQueue,
)

_ELEVATED_OR_ABOVE: frozenset[EscalationPriority] = frozenset(
    {EscalationPriority.ELEVATED, EscalationPriority.URGENT}
)
_REQUIRED_ELEVATED_REASONS: frozenset[EscalationReason] = frozenset(
    {EscalationReason.FINANCIAL_HARDSHIP, EscalationReason.VULNERABLE_CUSTOMER}
)
_REVIEWER_ESCALATION_EXCLUDED_REASONS: frozenset[EscalationReason] = frozenset(
    {EscalationReason.REQUEST_HUMAN, EscalationReason.UNRESOLVED_UNKNOWN}
)
_REQUIRED_FALLBACK = (ReviewQueue.COLLECTIONS_REVIEW, ReviewerRole.COLLECTIONS_OFFICER)


class PolicyValidationError(Exception):
    """A named, contract-validation failure identifying the offending parameter."""

    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"Invalid policy parameter '{parameter}': {reason}")


def validate_policy_parameters(raw_parameters: Any) -> PolicyParameters:
    """Validate raw (JSON-decoded) data against the full policy contract.

    Raises `PolicyValidationError` naming the first invalid parameter found,
    whether the failure is structural (missing/wrong-typed/out-of-range field)
    or a cross-field contract rule.
    """
    parameters = _parse_structural(raw_parameters)
    _validate_priority(parameters)
    _validate_ptp(parameters)
    _validate_payment(parameters)
    _validate_arrangement_and_exception(parameters)
    _validate_routing(parameters)
    return parameters


def _parse_structural(raw_parameters: Any) -> PolicyParameters:
    try:
        return PolicyParameters.model_validate(raw_parameters)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        parameter = ".".join(str(part) for part in first_error["loc"])
        raise PolicyValidationError(
            parameter=parameter or "<root>", reason=first_error["msg"]
        ) from exc


def _validate_priority(parameters: PolicyParameters) -> None:
    weights = parameters.priority.weights
    weight_sum = (
        weights.dpd
        + weights.overdue_amount
        + weights.broken_ptp_count
        + weights.recent_contact_outcome
    )
    if weight_sum <= 0:
        raise PolicyValidationError(
            "priority.weights", "sum of the four priority weights must be greater than 0"
        )

    low_cutoff, high_cutoff = parameters.priority.band_cutoffs
    if not (Decimal(0) <= low_cutoff < high_cutoff <= weight_sum):
        raise PolicyValidationError(
            "priority.band_cutoffs",
            "band_cutoffs must be strictly ascending and within [0, sum of weights]",
        )

    score_keys = set(parameters.priority.contact_outcome_scores.keys())
    if score_keys != set(ContactOutcome):
        raise PolicyValidationError(
            "priority.contact_outcome_scores",
            "contact_outcome_scores must contain exactly every ContactOutcome value",
        )


def _validate_ptp(parameters: PolicyParameters) -> None:
    ptp = parameters.ptp
    if ptp.min_amount.amount <= 0:
        raise PolicyValidationError("ptp.min_amount", "min_amount must be greater than 0")
    if ptp.qualifying_payment_min_amount.amount <= 0:
        raise PolicyValidationError(
            "ptp.qualifying_payment_min_amount",
            "qualifying_payment_min_amount must be greater than 0",
        )
    if ptp.qualifying_payment_min_amount > ptp.min_amount:
        raise PolicyValidationError(
            "ptp.qualifying_payment_min_amount",
            "qualifying_payment_min_amount must be <= ptp.min_amount",
        )
    if parameters.priority.normalization.overdue_amount.amount <= 0:
        raise PolicyValidationError(
            "priority.normalization.overdue_amount",
            "normalization.overdue_amount must be greater than 0",
        )


def _validate_payment(parameters: PolicyParameters) -> None:
    options = parameters.payment.payable_options
    if len(options) != len(set(options)):
        raise PolicyValidationError(
            "payment.payable_options", "payable_options must not contain duplicates"
        )


def _validate_arrangement_and_exception(parameters: PolicyParameters) -> None:
    arrangement = parameters.arrangement
    counts = arrangement.installment_counts
    if list(counts) != sorted(set(counts)) or len(counts) != len(set(counts)):
        raise PolicyValidationError(
            "arrangement.installment_counts",
            "installment_counts must be unique and strictly ascending",
        )
    if arrangement.min_overdue_amount.amount <= 0:
        raise PolicyValidationError(
            "arrangement.min_overdue_amount", "min_overdue_amount must be greater than 0"
        )
    if arrangement.min_installment_amount.amount <= 0:
        raise PolicyValidationError(
            "arrangement.min_installment_amount",
            "min_installment_amount must be greater than 0",
        )

    thresholds = parameters.exception.thresholds
    if thresholds.max_installment_count <= max(counts):
        raise PolicyValidationError(
            "exception.thresholds.max_installment_count",
            "max_installment_count must be greater than max(arrangement.installment_counts)",
        )
    if thresholds.max_start_delay_days < arrangement.max_start_delay_days:
        raise PolicyValidationError(
            "exception.thresholds.max_start_delay_days",
            "max_start_delay_days must be >= arrangement.max_start_delay_days",
        )
    if thresholds.min_installment_amount.amount <= 0:
        raise PolicyValidationError(
            "exception.thresholds.min_installment_amount",
            "min_installment_amount must be greater than 0",
        )
    if thresholds.min_installment_amount > arrangement.min_installment_amount:
        raise PolicyValidationError(
            "exception.thresholds.min_installment_amount",
            "min_installment_amount must be <= arrangement.min_installment_amount",
        )

    officer_types = parameters.exception.authority.collections_officer.types
    if len(officer_types) != len(set(officer_types)):
        raise PolicyValidationError(
            "exception.authority.collections_officer.types",
            "collections_officer.types must not contain duplicates",
        )


def _validate_routing(parameters: PolicyParameters) -> None:
    routing = parameters.routing
    table_keys = set(routing.table.keys())
    all_reasons = set(EscalationReason)
    if table_keys != all_reasons:
        raise PolicyValidationError(
            "routing.table",
            f"routing.table must contain exactly the {len(all_reasons)} EscalationReason "
            f"keys; missing={sorted(r.value for r in all_reasons - table_keys)}, "
            f"unexpected={sorted(r.value for r in table_keys - all_reasons)}",
        )

    if (routing.fallback.queue, routing.fallback.reviewer_role) != _REQUIRED_FALLBACK:
        raise PolicyValidationError(
            "routing.fallback",
            f"fallback must equal {{queue: {_REQUIRED_FALLBACK[0]}, "
            f"reviewer_role: {_REQUIRED_FALLBACK[1]}}}",
        )

    priority_keys = set(routing.priority_by_reason.keys())
    if priority_keys != all_reasons:
        raise PolicyValidationError(
            "routing.priority_by_reason",
            f"priority_by_reason must contain exactly the {len(all_reasons)} "
            "EscalationReason keys",
        )
    for reason in _REQUIRED_ELEVATED_REASONS:
        if routing.priority_by_reason[reason] not in _ELEVATED_OR_ABOVE:
            raise PolicyValidationError(
                "routing.priority_by_reason",
                f"{reason.value} must be at least ELEVATED",
            )

    reviewer_reasons = set(routing.reviewer_escalation_reasons)
    if reviewer_reasons & _REVIEWER_ESCALATION_EXCLUDED_REASONS:
        raise PolicyValidationError(
            "routing.reviewer_escalation_reasons",
            "reviewer_escalation_reasons must exclude REQUEST_HUMAN and UNRESOLVED_UNKNOWN",
        )

    aging_keys = set(routing.aging_warning_hours.keys())
    if aging_keys != set(EscalationPriority):
        raise PolicyValidationError(
            "routing.aging_warning_hours",
            "aging_warning_hours must contain exactly the 3 EscalationPriority keys",
        )
