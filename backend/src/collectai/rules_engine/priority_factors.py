"""Per-factor score computation for the Collections Priority calculation.

Split out of `priority.py` (E2-S4) to keep that module under the code-gen
skill's 300-line block threshold, per that module's own docstring note ("if
it grows further ... split the per-factor builders ... into a
priority_factors.py submodule"). Pure `Decimal` math over one factor at a
time; `priority.py` owns assembling these into a full score and
`PriorityResult`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from collectai.config.policy.models import PriorityParameters
from collectai.types.enums import ContactOutcome
from collectai.types.money import Money

_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class RawFactor:
    """Internal, full-precision form of a `Factor` before string formatting."""

    factor_id: str
    attribute: str
    value: str
    normalized: Decimal
    weight: Decimal
    contribution: Decimal


def dpd_factor(priority: PriorityParameters, dpd: int) -> RawFactor:
    normalized = _clamp_ratio(Decimal(dpd), Decimal(priority.normalization.dpd_days))
    return _make_raw_factor("dpd", "dpd", str(dpd), normalized, priority.weights.dpd)


def overdue_amount_factor(priority: PriorityParameters, overdue_amount: Money) -> RawFactor:
    normalized = _clamp_ratio(
        overdue_amount.amount, priority.normalization.overdue_amount.amount
    )
    return _make_raw_factor(
        "overdue_amount",
        "overdue_amount",
        overdue_amount.to_api_string(),
        normalized,
        priority.weights.overdue_amount,
    )


def broken_ptp_count_factor(priority: PriorityParameters, broken_ptp_count: int) -> RawFactor:
    normalized = _clamp_ratio(
        Decimal(broken_ptp_count), Decimal(priority.normalization.broken_ptp_count)
    )
    return _make_raw_factor(
        "broken_ptp_count",
        "broken_ptp_count",
        str(broken_ptp_count),
        normalized,
        priority.weights.broken_ptp_count,
    )


def recent_contact_outcome_factor(
    priority: PriorityParameters, outcome: ContactOutcome | None
) -> RawFactor:
    normalized = priority.contact_outcome_scores[outcome] if outcome is not None else _ZERO
    value = outcome.value if outcome is not None else "NONE"
    return _make_raw_factor(
        "recent_contact_outcome",
        "recent_contact_outcome",
        value,
        normalized,
        priority.weights.recent_contact_outcome,
    )


def _clamp_ratio(raw_value: Decimal, saturation_point: Decimal) -> Decimal:
    return min(raw_value / saturation_point, _ONE)


def _make_raw_factor(
    factor_id: str, attribute: str, value: str, normalized: Decimal, weight: Decimal
) -> RawFactor:
    contribution = (weight * normalized).quantize(_TWO_PLACES)
    return RawFactor(
        factor_id=factor_id,
        attribute=attribute,
        value=value,
        normalized=normalized,
        weight=weight,
        contribution=contribution,
    )
