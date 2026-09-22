"""Next-best-action and recommendation enums (api-contracts.md section 5)."""

from __future__ import annotations

from enum import StrEnum


class NbaAction(StrEnum):
    CONTACT_CUSTOMER = "CONTACT_CUSTOMER"
    REQUEST_PAYMENT = "REQUEST_PAYMENT"
    OFFER_ELIGIBLE_ARRANGEMENT = "OFFER_ELIGIBLE_ARRANGEMENT"
    FOLLOW_UP_PTP = "FOLLOW_UP_PTP"
    REFER_TO_HARDSHIP_WORKFLOW = "REFER_TO_HARDSHIP_WORKFLOW"
    ESCALATE_TO_HUMAN_REVIEW = "ESCALATE_TO_HUMAN_REVIEW"


class RecommendationStatus(StrEnum):
    GENERATED = "GENERATED"
    SAFE_FALLBACK = "SAFE_FALLBACK"
    HUMAN_REVIEW_ONLY = "HUMAN_REVIEW_ONLY"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    NOT_GENERATED = "NOT_GENERATED"


class RecommendationDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    OVERRIDDEN = "OVERRIDDEN"
