"""All enums mirrored from api-contracts.md section 5.

Split into topic sub-modules to stay under the 300-line block threshold; every
member is re-exported here so callers can keep writing
`from collectai.types.enums import EscalationReason` without knowing about
the split.
"""

from __future__ import annotations

from collectai.types.enums.account import (
    AccountType,
    Bucket,
    CollectionStatus,
    ItemKind,
    ItemStatus,
    PriorityBand,
)
from collectai.types.enums.conversation import (
    ContentSource,
    ConversationStatus,
    Intent,
    MessageLabel,
    MessageRole,
    SafeState,
    SpecialRequest,
)
from collectai.types.enums.escalation_review import (
    CaseStatus,
    ComplianceOutcome,
    DecisionKind,
    EligibilityClass,
    EscalationPriority,
    EscalationReason,
    ExceptionType,
    ReviewAction,
    ReviewQueue,
)
from collectai.types.enums.hardship_dispute import (
    DisputeCategory,
    DisputeOutcome,
    DisputeStatus,
    HardshipIndicatorType,
    HardshipStatus,
    VulnerabilityCategory,
)
from collectai.types.enums.interaction import (
    ContactOutcome,
    Freshness,
    InteractionChannel,
    InteractionDirection,
    SuppressionScope,
    SuppressionSource,
)
from collectai.types.enums.persona_actor import ActorKind, CaseSource, Persona, ReviewerRole
from collectai.types.enums.ptp_payment import (
    ArrangementCreatedVia,
    ArrangementStatus,
    PayableOptionType,
    PaymentOutcome,
    PaymentSource,
    ProposalKind,
    ProposalStatus,
    PtpSource,
    PtpStatus,
)
from collectai.types.enums.recommendation import (
    NbaAction,
    RecommendationDecision,
    RecommendationStatus,
)
from collectai.types.enums.system import (
    AuditStage,
    CaseSummaryKind,
    ClaimStatus,
    ClockMode,
    DataLabel,
    ErrorCode,
    KpiUnit,
    LlmMode,
    ProviderMode,
)

__all__ = [
    "AccountType",
    "ActorKind",
    "ArrangementCreatedVia",
    "ArrangementStatus",
    "AuditStage",
    "Bucket",
    "CaseSource",
    "CaseStatus",
    "CaseSummaryKind",
    "ClaimStatus",
    "ClockMode",
    "CollectionStatus",
    "ComplianceOutcome",
    "ContactOutcome",
    "ContentSource",
    "ConversationStatus",
    "DataLabel",
    "DecisionKind",
    "DisputeCategory",
    "DisputeOutcome",
    "DisputeStatus",
    "EligibilityClass",
    "ErrorCode",
    "EscalationPriority",
    "EscalationReason",
    "ExceptionType",
    "Freshness",
    "HardshipIndicatorType",
    "HardshipStatus",
    "Intent",
    "InteractionChannel",
    "InteractionDirection",
    "ItemKind",
    "ItemStatus",
    "KpiUnit",
    "LlmMode",
    "MessageLabel",
    "MessageRole",
    "NbaAction",
    "PayableOptionType",
    "PaymentOutcome",
    "PaymentSource",
    "Persona",
    "PriorityBand",
    "ProposalKind",
    "ProposalStatus",
    "ProviderMode",
    "PtpSource",
    "PtpStatus",
    "RecommendationDecision",
    "RecommendationStatus",
    "ReviewAction",
    "ReviewQueue",
    "ReviewerRole",
    "SafeState",
    "SpecialRequest",
    "SuppressionScope",
    "SuppressionSource",
    "VulnerabilityCategory",
]
