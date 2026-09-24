"""Pydantic response models for the Customer 360 read model (E4-S1;
api-contracts.md 3.4 `GET /api/customers/{account_id}/360`, section 4
schemas `Customer360`, `ProfileBlock`, `AccountBlock`, `DelinquentItem`,
`SuppressionEntry`, `TreatmentBlock`, `DeterministicBlock`, `Recommendation`,
`AiBlock`, `Interaction`, `PromiseToPay`, `HardshipIndicator`,
`HardshipCase`, `Dispute`, `EscalationSummary`, `EscalationBlock`,
`SnapshotInfo`, `Factor`, `PriorityResult`).

Every field mirrors the wire contract's name, type and requiredness. `Factor`
and `PriorityResult` are re-declared here as Pydantic models -- the
`rules_engine.priority` versions of the same names are plain dataclasses used
internally by the rules engine; `domain_services.customer360_service` maps
one to the other at the API boundary, the same boundary every other
`domain_services` module in this codebase already crosses when it returns a
Pydantic domain model (e.g. `types.models.delinquency_record.DelinquencyRecord`).

`payment_events` (E6-S3, E4-S2 AC4) reuses `api.schemas.me.PaymentEvent`
verbatim rather than a second, field-for-field duplicate of the exact same
shape -- both `customer360.py` and `customer360_mapping.py` were already at
the code-gen skill's 300-line block threshold, so this file keeps its own
"re-declare every shape" convention everywhere except this one field.
`arrangements` stays `list[Any] = []`: `PaymentArrangement` still belongs to
not-yet-built E8-S1.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from collectai.api.schemas.me import PaymentEvent
from collectai.types.enums import (
    AccountType,
    Bucket,
    CaseStatus,
    CollectionStatus,
    ContactOutcome,
    ContentSource,
    DisputeCategory,
    DisputeOutcome,
    DisputeStatus,
    EscalationPriority,
    EscalationReason,
    Freshness,
    HardshipIndicatorType,
    HardshipStatus,
    InteractionChannel,
    InteractionDirection,
    ItemKind,
    ItemStatus,
    NbaAction,
    PayableOptionType,
    Persona,
    PriorityBand,
    PtpSource,
    PtpStatus,
    RecommendationDecision,
    RecommendationStatus,
    ReviewQueue,
    SuppressionScope,
    SuppressionSource,
    VulnerabilityCategory,
)
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode


class _Frozen(BaseModel):
    """Base for every Customer 360 response model: immutable, response-only."""

    model_config = ConfigDict(frozen=True)


class Factor(_Frozen):
    factor_id: str
    attribute: str
    value: str
    normalized_value: str
    weight: str
    contribution: str


class PriorityResult(_Frozen):
    score: str
    band: PriorityBand
    factors: list[Factor]
    policy_version: str


class SnapshotInfo(_Frozen):
    as_of: datetime | None
    record_version: int
    freshness: Freshness
    freshness_reason_code: str | None
    max_age_minutes: int


class ProfileBlock(_Frozen):
    customer_id: str
    display_name: str
    email: str
    phone: str
    vulnerability_flag: bool
    vulnerability_category: VulnerabilityCategory | None


class AccountBlock(_Frozen):
    account_id: str
    account_type: AccountType
    product_name: str
    currency: str
    opened_on: date
    outstanding_balance: Money
    overdue_amount: Money
    undisputed_overdue_amount: Money
    dpd: int
    bucket: Bucket
    collection_status: CollectionStatus
    product_attributes: dict[str, Any]


class DelinquentItem(_Frozen):
    item_id: str
    kind: ItemKind
    label: str
    amount_outstanding: Money
    due_date: date
    status: ItemStatus
    disputed: bool


class SuppressionEntry(_Frozen):
    source_type: SuppressionSource
    source_id: str
    scope: SuppressionScope
    item_id: str | None


class TreatmentBlock(_Frozen):
    human_treatment: bool
    automated_treatment_suppressed: bool
    suppressions: list[SuppressionEntry]


class ContactPolicyResult(_Frozen):
    contact_allowed: bool
    reason_code: ReasonCode | None
    next_allowed_at: datetime | None
    attempts_in_period: int


class PayableOption(_Frozen):
    option: PayableOptionType
    amount: Money


class RecordCheck(_Frozen):
    consistent: bool
    reason_code: ReasonCode | None


class DeterministicBlock(_Frozen):
    source: Literal["deterministic"] = "deterministic"
    label: Literal["Rules engine"] = "Rules engine"
    policy_version: str | None
    status: Literal["OK", "POLICY_UNAVAILABLE"]
    priority: PriorityResult | None
    treatment: TreatmentBlock
    contact_policy: ContactPolicyResult | None
    payable_options: list[PayableOption]
    record_check: RecordCheck


class Recommendation(_Frozen):
    recommendation_id: str
    account_id: str
    source: Literal["ai"] = "ai"
    action: NbaAction
    rationale: str
    referenced_factor_ids: list[str]
    status: RecommendationStatus
    content_source: ContentSource
    model_id: str | None
    prompt_version: str | None
    policy_version: str
    record_version: int
    created_at: datetime
    audit_event_id: str
    officer_decision: RecommendationDecision | None


class AiBlock(_Frozen):
    source: Literal["ai"] = "ai"
    label: Literal["AI-generated"] = "AI-generated"
    status: RecommendationStatus
    recommendation: Recommendation | None


class Interaction(_Frozen):
    interaction_id: str
    channel: InteractionChannel
    direction: InteractionDirection
    outcome: ContactOutcome | None
    occurred_at: datetime
    summary: str
    counts_as_attempt: bool
    conversation_id: str | None


class PromiseToPay(_Frozen):
    ptp_id: str
    account_id: str
    promised_amount: Money
    promised_date: date
    status: PtpStatus
    cumulative_paid: Money
    remaining_amount: Money
    interaction_reference: str | None
    source: PtpSource
    created_by_persona: Persona
    created_at: datetime
    updated_at: datetime
    kept_at: datetime | None
    broken_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    policy_version: str
    version: int


class HardshipIndicator(_Frozen):
    indicator_type: HardshipIndicatorType
    customer_statement: str


class HardshipCase(_Frozen):
    hardship_case_id: str
    account_id: str
    customer_id: str
    conversation_id: str | None
    status: HardshipStatus
    indicators: list[HardshipIndicator]
    escalation_case_id: str | None
    created_at: datetime
    decided_at: datetime | None


class Dispute(_Frozen):
    dispute_id: str
    account_id: str
    customer_id: str
    item_id: str | None
    category: DisputeCategory
    customer_reason: str
    status: DisputeStatus
    outcome: DisputeOutcome | None
    resolution_reason: str | None
    conversation_id: str | None
    escalation_case_id: str | None
    created_at: datetime
    resolved_at: datetime | None
    version: int


class EscalationSummary(_Frozen):
    case_id: str
    reason: EscalationReason
    status: CaseStatus
    priority: EscalationPriority
    queue: ReviewQueue
    created_at: datetime


class EscalationBlock(_Frozen):
    badge: str | None
    has_open_case: bool
    cases: list[EscalationSummary]


class Customer360(_Frozen):
    account_id: str
    generated_at: datetime
    snapshot: SnapshotInfo
    profile: ProfileBlock
    account: AccountBlock
    items: list[DelinquentItem]
    deterministic: DeterministicBlock
    ai: AiBlock
    interactions: list[Interaction]
    ptp_history: list[PromiseToPay]
    payment_events: list[PaymentEvent] = []
    arrangements: list[Any] = []
    hardship_cases: list[HardshipCase]
    disputes: list[Dispute]
    escalation: EscalationBlock
