"""Deterministic-fact assembly for one next-best-action generation call
(E4-S3 AC1, AC2).

Builds the *inputs* an AI call and its guardrails need from an already-
assembled `Customer360` read model: the allow-listed prompt context
(`ai_orchestration.prompts.builder.AllowedPromptContext`, E5-S3 AC4), the
set of factor ids the model may cite (AC2), and the `GroundedFacts` its
rationale is checked against (AC2). Every value here traces back to
`rules_engine.priority.compute_priority` or the account/delinquency record
`Customer360` itself already read -- nothing here is free-form.
"""

from __future__ import annotations

from collectai.ai_orchestration.grounding import GroundedFacts
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.api.schemas.customer360 import Customer360


def allowed_factor_ids(customer360: Customer360) -> frozenset[str]:
    priority = customer360.deterministic.priority
    assert priority is not None  # noqa: S101 - caller checks deterministic.status == "OK" first
    return frozenset(factor.factor_id for factor in priority.factors)


def grounded_facts(customer360: Customer360) -> GroundedFacts:
    return GroundedFacts(
        currency_amounts=frozenset(
            {
                customer360.account.overdue_amount.to_api_string(),
                customer360.account.outstanding_balance.to_api_string(),
            }
        ),
        dates=frozenset(),
        option_ids=frozenset(),
    )


def build_prompt_context(customer360: Customer360) -> AllowedPromptContext:
    priority = customer360.deterministic.priority
    assert priority is not None  # noqa: S101 - caller checks deterministic.status == "OK" first
    return AllowedPromptContext(
        customer_display_name=customer360.profile.display_name,
        account_reference=customer360.account_id,
        delinquency_summary=_delinquency_summary(customer360),
        priority_band=priority.band.value,
        eligible_options_summary=None,
    )


def _delinquency_summary(customer360: Customer360) -> str:
    priority = customer360.deterministic.priority
    assert priority is not None  # noqa: S101 - caller checks deterministic.status == "OK" first
    account = customer360.account
    factor_parts = "; ".join(f"{factor.factor_id}={factor.value}" for factor in priority.factors)
    return (
        f"DPD {account.dpd}, overdue amount {account.overdue_amount.to_api_string()} "
        f"{account.currency}, outstanding balance {account.outstanding_balance.to_api_string()} "
        f"{account.currency}. Priority factors (factor_id=value): {factor_parts}."
    )


__all__ = ["allowed_factor_ids", "build_prompt_context", "grounded_facts"]
