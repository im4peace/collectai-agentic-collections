"""Deterministic Collections Priority score, band and contributing factors.

specs/policy-ruleset-contract.md section 3.1 defines the four weighted
factors (dpd, overdue_amount, broken_ptp_count, recent_contact_outcome);
specs/design/api-contracts.md defines the `Factor` and `PriorityResult`
wire shapes this module mirrors. Every calculation is exact `Decimal`
arithmetic so the score is perfectly reproducible for identical inputs and
policy version (AC1).

NOTE -- E2-S4 suppression integration: `human_treatment` and
`automated_treatment_suppressed` on `PriorityResult` are computed by
`_compute_treatment_flags`, which now delegates to the full suppression
engine (`rules_engine/suppression.py::evaluate_suppression`) instead of
OR-ing three booleans itself. `PriorityInput`'s three boolean fields
(`has_active_dispute`/`has_active_hardship`/`has_open_escalation`) and
`compute_priority`'s public signature are unchanged -- only what feeds the
two flags changed, not the contract.

NOTE -- file size: the per-factor builders that used to live here
(`_dpd_factor`, `_overdue_amount_factor`, `_broken_ptp_count_factor`,
`_recent_contact_outcome_factor`) were split out into `priority_factors.py`
(E2-S4) once E2-S4's suppression integration pushed this module past the
300-line block threshold (code-gen skill principle #1). `PriorityInput`,
`Factor`, `PriorityResult` and `compute_priority` stay here; the pure
per-factor `Decimal` math is re-exported from `priority_factors`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from collectai.config.policy.models import PolicyRuleSet, PriorityParameters
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.priority_factors import (
    RawFactor,
    broken_ptp_count_factor,
    dpd_factor,
    overdue_amount_factor,
    recent_contact_outcome_factor,
)
from collectai.rules_engine.suppression import SuppressionInput, evaluate_suppression
from collectai.types.enums import ContactOutcome, PriorityBand
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable, RuleFailure, RuleResult

_TWO_PLACES = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")
_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class PriorityInput:
    """Plain, already-fetched inputs for one delinquent account.

    A future `domain_services` story reads these from persistence; this
    service only ever receives already-resolved values, never a DB handle.
    """

    dpd: int
    overdue_amount: Money
    broken_ptp_count: int
    recent_contact_outcome: ContactOutcome | None
    has_active_dispute: bool
    has_active_hardship: bool
    has_open_escalation: bool


@dataclass(frozen=True, slots=True)
class Factor:
    """One contributing factor of the score (api-contracts.md `Factor`)."""

    factor_id: str
    attribute: str
    value: str
    normalized_value: str
    weight: str
    contribution: str


@dataclass(frozen=True, slots=True)
class PriorityResult:
    """Deterministic Collections Priority (api-contracts.md `PriorityResult`)
    plus the narrow human-treatment seam described in the module docstring.
    """

    score: str
    band: PriorityBand
    factors: list[Factor]
    policy_version: str
    human_treatment: bool
    automated_treatment_suppressed: bool


def compute_priority(
    priority_input: PriorityInput, policy_provider: PolicyProvider
) -> RuleResult[PriorityResult]:
    """Compute the deterministic priority score, band and factors.

    Fail-closed (AC6): if no policy is active, or the active policy's
    priority parameters are not usable for this input (e.g. a non-ascending
    `band_cutoffs`, a saturation point of zero, or a `contact_outcome_scores`
    map missing the given outcome), returns a `RuleFailure` carrying
    `ReasonCode.POLICY_UNAVAILABLE` with no score produced.
    """
    try:
        rule_set = policy_provider.get_active()
    except PolicyUnavailable as exc:
        return RuleResult.fail(RuleFailure(reason_code=exc.reason_code, message=str(exc)))

    priority_params = rule_set.parameters.priority
    invalid = _check_usable_parameters(priority_params, priority_input.recent_contact_outcome)
    if invalid is not None:
        return RuleResult.fail(invalid)

    raw_factors = _build_raw_factors(priority_params, priority_input)
    score = sum((factor.contribution for factor in raw_factors), start=_ZERO).quantize(
        _TWO_PLACES
    )
    band = _resolve_band(score, priority_params.band_cutoffs)
    human_treatment, automated_treatment_suppressed = _compute_treatment_flags(
        priority_input, rule_set
    )

    result = PriorityResult(
        score=_format_decimal(score, _TWO_PLACES),
        band=band,
        factors=_ordered_factors(raw_factors),
        policy_version=rule_set.policy_version,
        human_treatment=human_treatment,
        automated_treatment_suppressed=automated_treatment_suppressed,
    )
    return RuleResult.success(result)


def _check_usable_parameters(
    priority: PriorityParameters, outcome: ContactOutcome | None
) -> RuleFailure | None:
    """Defence-in-depth: the values needed to divide and to band safely.

    A `PolicyRuleSet` normally reaches this service already validated by
    `config.policy.validator` (which enforces these same rules), but this
    service never trusts that as its only safeguard -- it is the one place
    every rules-engine caller relies on to fail closed (AC6).
    """
    if priority.normalization.overdue_amount.amount <= _ZERO:
        return _policy_unavailable(
            "priority.normalization.overdue_amount must be greater than 0"
        )
    low_cutoff, high_cutoff = priority.band_cutoffs
    if not low_cutoff < high_cutoff:
        return _policy_unavailable("priority.band_cutoffs must be strictly ascending")
    if outcome is not None and outcome not in priority.contact_outcome_scores:
        return _policy_unavailable(
            f"priority.contact_outcome_scores is missing an entry for {outcome.value}"
        )
    return None


def _policy_unavailable(message: str) -> RuleFailure:
    return RuleFailure(reason_code=ReasonCode.POLICY_UNAVAILABLE, message=message)


def _build_raw_factors(
    priority: PriorityParameters, priority_input: PriorityInput
) -> list[RawFactor]:
    return [
        dpd_factor(priority, priority_input.dpd),
        overdue_amount_factor(priority, priority_input.overdue_amount),
        broken_ptp_count_factor(priority, priority_input.broken_ptp_count),
        recent_contact_outcome_factor(priority, priority_input.recent_contact_outcome),
    ]


def _resolve_band(score: Decimal, band_cutoffs: list[Decimal]) -> PriorityBand:
    low_cutoff, high_cutoff = band_cutoffs
    if score < low_cutoff:
        return PriorityBand.LOW
    if score < high_cutoff:
        return PriorityBand.MEDIUM
    return PriorityBand.HIGH


def _ordered_factors(raw_factors: list[RawFactor]) -> list[Factor]:
    """Ordered by contribution descending, then factor_id ascending."""
    ordered = sorted(raw_factors, key=lambda factor: (-factor.contribution, factor.factor_id))
    return [_to_public_factor(factor) for factor in ordered]


def _to_public_factor(raw: RawFactor) -> Factor:
    return Factor(
        factor_id=raw.factor_id,
        attribute=raw.attribute,
        value=raw.value,
        normalized_value=_format_decimal(raw.normalized, _FOUR_PLACES),
        weight=_format_decimal(raw.weight, None),
        contribution=_format_decimal(raw.contribution, _TWO_PLACES),
    )


def _format_decimal(value: Decimal, places: Decimal | None) -> str:
    quantized = value.quantize(places) if places is not None else value
    return format(quantized, "f")


def _compute_treatment_flags(
    priority_input: PriorityInput, rule_set: PolicyRuleSet
) -> tuple[bool, bool]:
    """Delegate to `rules_engine.suppression.evaluate_suppression` (E2-S4).

    `PriorityInput` carries only the three legacy account-wide booleans (no
    case/dispute ids and no `item_id` -- this seam only ever evaluates at
    account level). They are translated into a `SuppressionInput` with
    placeholder source ids (`evaluate_suppression` falls back to "unknown"
    for a missing id); a future `domain_services` caller that has real ids
    and a specific item will call `evaluate_suppression` directly instead of
    going through this narrower seam. See the module docstring for why this
    is deliberately kept separate from the four-factor scoring math above.
    """
    suppression_input = SuppressionInput(
        has_open_escalation=priority_input.has_open_escalation,
        escalation_case_id=None,
        has_active_hardship=priority_input.has_active_hardship,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[("unknown", None)] if priority_input.has_active_dispute else [],
    )
    treatment_block = evaluate_suppression(suppression_input, rule_set)
    return treatment_block.human_treatment, treatment_block.automated_treatment_suppressed
