"""Pydantic models for `PolicyRuleSet` and its nested `PolicyParameters`.

Shape and constraints come from `specs/policy-ruleset-contract.md` section 3 and
`specs/design/data-models.md`'s `policy_rule_set` table. This module defines
*structural* validation only (field types, simple per-field ranges expressible
declaratively). Cross-field and cross-section rules (band-cutoff ordering,
routing-table completeness, etc.) live in `collectai.config.policy.validator`,
which is the single place that raises the named `PolicyValidationError`
required by the contract.

Every model is frozen: a `PolicyRuleSet` is immutable per version, so changing
a parameter means constructing a new instance (a new version), never mutating
one in place.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from collectai.types.enums import (
    ContactOutcome,
    EscalationPriority,
    EscalationReason,
    ExceptionType,
    PayableOptionType,
    ReviewerRole,
    ReviewQueue,
    SuppressionScope,
    VulnerabilityCategory,
)
from collectai.types.money import Money

_Weight = Annotated[Decimal, Field(ge=0)]
_UnitFraction = Annotated[Decimal, Field(ge=0, le=1)]


class _StrictModel(BaseModel):
    """Base for every policy model: immutable, no undeclared fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PriorityWeights(_StrictModel):
    dpd: _Weight
    overdue_amount: _Weight
    broken_ptp_count: _Weight
    recent_contact_outcome: _Weight


class PriorityNormalization(_StrictModel):
    dpd_days: Annotated[int, Field(ge=1)]
    overdue_amount: Money
    broken_ptp_count: Annotated[int, Field(ge=1)]


class PriorityParameters(_StrictModel):
    weights: PriorityWeights
    normalization: PriorityNormalization
    contact_outcome_scores: dict[ContactOutcome, _UnitFraction]
    band_cutoffs: Annotated[list[Decimal], Field(min_length=2, max_length=2)]


class PtpParameters(_StrictModel):
    window_days: Annotated[int, Field(ge=1, le=365)]
    min_amount: Money
    qualifying_payment_min_amount: Money


class PaymentParameters(_StrictModel):
    payable_options: Annotated[list[PayableOptionType], Field(min_length=1)]


class ArrangementParameters(_StrictModel):
    eligible_max_dpd: Annotated[int, Field(ge=0)]
    min_overdue_amount: Money
    installment_counts: Annotated[
        list[Annotated[int, Field(ge=2, le=60)]], Field(min_length=1)
    ]
    min_installment_amount: Money
    max_start_delay_days: Annotated[int, Field(ge=0, le=90)]
    allow_with_active_ptp: bool


class ExceptionThresholds(_StrictModel):
    max_installment_count: Annotated[int, Field(ge=1, le=120)]
    max_start_delay_days: Annotated[int, Field(ge=0, le=180)]
    min_installment_amount: Money


class CollectionsOfficerAuthority(_StrictModel):
    types: list[ExceptionType]
    max_overdue_amount: Money


class ExceptionAuthority(_StrictModel):
    collections_officer: CollectionsOfficerAuthority


class ExceptionParameters(_StrictModel):
    thresholds: ExceptionThresholds
    authority: ExceptionAuthority


class ContactParameters(_StrictModel):
    max_attempts: Annotated[int, Field(ge=1)]
    period_days: Annotated[int, Field(ge=1)]
    min_interval_hours: Annotated[int, Field(ge=0)]


class FreshnessParameters(_StrictModel):
    max_snapshot_age_minutes: Annotated[int, Field(ge=1, le=10080)]


class SuppressionParameters(_StrictModel):
    dispute_scope: SuppressionScope
    hardship_scope: SuppressionScope
    vulnerable_scope: SuppressionScope
    release: Literal["HUMAN_DECISION"]


class VulnerabilityParameters(_StrictModel):
    categories: Annotated[list[VulnerabilityCategory], Field(min_length=1)]


class RoutingDestination(_StrictModel):
    queue: ReviewQueue
    reviewer_role: ReviewerRole


class RoutingParameters(_StrictModel):
    table: dict[EscalationReason, RoutingDestination]
    fallback: RoutingDestination
    priority_by_reason: dict[EscalationReason, EscalationPriority]
    reviewer_escalation_reasons: Annotated[list[EscalationReason], Field(min_length=1)]
    aging_warning_hours: dict[EscalationPriority, Annotated[int, Field(ge=1)]]


class ComplianceParameters(_StrictModel):
    review_outcomes: Annotated[list[str], Field(min_length=1)]


class PolicyParameters(_StrictModel):
    """Every contract parameter (specs/policy-ruleset-contract.md section 3)."""

    priority: PriorityParameters
    ptp: PtpParameters
    payment: PaymentParameters
    arrangement: ArrangementParameters
    exception: ExceptionParameters
    contact: ContactParameters
    freshness: FreshnessParameters
    suppression: SuppressionParameters
    vulnerability: VulnerabilityParameters
    routing: RoutingParameters
    compliance: ComplianceParameters


class PolicyRuleSet(_StrictModel):
    """Immutable, versioned rule set (`policy_rule_set` in data-models.md).

    Exactly one version is active at a time (enforced by
    `collectai.config.policy.provider.PolicyProvider`, not by this model).
    """

    policy_version: Annotated[str, Field(min_length=1)]
    parameters: PolicyParameters
    content_hash: str
    is_active: bool
    created_at: datetime
    activated_at: datetime | None


def compute_content_hash(parameters: PolicyParameters) -> str:
    """SHA-256 hex digest of the canonical (sorted-key) JSON of `parameters`.

    Tamper detection per data-models.md's `policy_rule_set.content_hash`: two
    `PolicyParameters` with identical values always hash identically,
    regardless of field insertion order.
    """
    canonical_json = json.dumps(
        parameters.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
