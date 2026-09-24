"""AC3: deterministic governance override for next-best-action generation
(E4-S3).

`Customer360.deterministic.treatment.human_treatment` already encodes
exactly the conditions api-contracts.md 3.5's POST behaviour lists: "Accounts
under dispute, hardship, vulnerable flag or open escalation always return
HUMAN_REVIEW_ONLY with action ESCALATE_TO_HUMAN_REVIEW regardless of model
output" (`rules_engine.suppression.evaluate_suppression` -- E2-S4 -- is the
single deterministic source of that flag). `recommendation_flow.py` checks
this with a plain Python `if` *before* any AI call is even made: the model
is never asked to respect this boundary and never given the chance to
override it (CLAUDE.md: "never delegate financial or binding decisions to
an LLM").
"""

from __future__ import annotations

from collectai.api.schemas.customer360 import Customer360

GOVERNANCE_HOLD_RATIONALE = (
    "This account has an active dispute, hardship case, open escalation or "
    "vulnerable-customer flag, so it requires human review before any "
    "further collections action."
)


def requires_human_review(customer360: Customer360) -> bool:
    """AC3: true when treatment is suppressed for a governance reason
    (dispute, hardship, open escalation or vulnerable-customer flag)."""
    return customer360.deterministic.treatment.human_treatment


__all__ = ["GOVERNANCE_HOLD_RATIONALE", "requires_human_review"]
