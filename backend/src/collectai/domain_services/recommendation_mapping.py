"""`RecommendationOrm` -> `api.schemas.customer360.Recommendation` wire
mapping (E4-S3).

Public (unlike most of `customer360_mapping.py`'s helpers, which are private
to `customer360_service.py`): both `customer360_service.py` (Customer 360's
`AiBlock`, via `_customer360_ai_block.py`) and `application
.recommendation_flow` (the GET/POST/decision recommendation endpoints) need
the exact same mapping and must never disagree about it. `application` may
import from `domain_services` (this package sits below it in the layering);
the reverse is never true, so this mapping lives here, not in `application`.
"""

from __future__ import annotations

from collectai.api.schemas.customer360 import Recommendation
from collectai.persistence.orm.recommendation import RecommendationOrm
from collectai.types.enums import (
    ContentSource,
    NbaAction,
    RecommendationDecision,
    RecommendationStatus,
)


def to_recommendation_schema(row: RecommendationOrm) -> Recommendation:
    return Recommendation(
        recommendation_id=row.recommendation_id,
        account_id=row.account_id,
        action=NbaAction(row.action),
        rationale=row.rationale,
        referenced_factor_ids=list(row.referenced_factor_ids),
        status=RecommendationStatus(row.status),
        content_source=ContentSource(row.content_source),
        model_id=row.model_id,
        prompt_version=row.prompt_version,
        policy_version=row.policy_version,
        record_version=row.record_version,
        created_at=row.created_at,
        audit_event_id=row.audit_event_id,
        officer_decision=(
            RecommendationDecision(row.officer_decision) if row.officer_decision else None
        ),
    )


__all__ = ["to_recommendation_schema"]
