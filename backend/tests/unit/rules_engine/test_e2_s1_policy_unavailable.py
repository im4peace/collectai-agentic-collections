"""E2-S1 AC6: missing or invalid priority parameters fail closed.

`compute_priority` reads priority parameters from the active `PolicyRuleSet`.
When there is no active rule set, or the active rule set's priority
parameters are not usable for the given input, the service returns
`RuleFailure(reason_code=POLICY_UNAVAILABLE)` with no score produced -- it
never raises, and never returns a partially-computed `PriorityResult`.

Structural contract violations (e.g. `band_cutoffs` out of order, an
incomplete `contact_outcome_scores` map) are normally rejected before a
`PolicyRuleSet` is ever registered, by `config.policy.validator`. These
tests bypass that validator on purpose (constructing the models directly)
to exercise the rules-engine service's own defence-in-depth checks.
"""

from __future__ import annotations

from decimal import Decimal

from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.priority import PriorityInput, compute_priority
from collectai.types.clock import SimulatedClock
from collectai.types.enums import ContactOutcome
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode


def _default_input(recent_contact_outcome: ContactOutcome | None = None) -> PriorityInput:
    return PriorityInput(
        dpd=10,
        overdue_amount=Money("100.00"),
        broken_ptp_count=0,
        recent_contact_outcome=recent_contact_outcome,
        has_active_dispute=False,
        has_active_hardship=False,
        has_open_escalation=False,
    )


def test_no_active_policy_returns_policy_unavailable() -> None:
    provider = PolicyProvider()

    result = compute_priority(_default_input(), provider)

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE


def test_registered_but_inactive_policy_returns_policy_unavailable(
    policy_v1: PolicyRuleSet,
) -> None:
    provider = PolicyProvider()
    provider.register(policy_v1)

    result = compute_priority(_default_input(), provider)

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE


def test_non_ascending_band_cutoffs_returns_policy_unavailable(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> None:
    tampered_priority = policy_v1.parameters.priority.model_copy(
        update={"band_cutoffs": [Decimal("65"), Decimal("35")]}
    )
    tampered_parameters = policy_v1.parameters.model_copy(
        update={"priority": tampered_priority}
    )
    tampered_rule_set = policy_v1.model_copy(update={"parameters": tampered_parameters})

    provider = PolicyProvider()
    provider.register(tampered_rule_set)
    provider.activate("policy-v1", clock)

    result = compute_priority(_default_input(), provider)

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE


def test_missing_contact_outcome_score_entry_returns_policy_unavailable(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> None:
    incomplete_scores = dict(policy_v1.parameters.priority.contact_outcome_scores)
    del incomplete_scores[ContactOutcome.PTP_BROKEN]
    tampered_priority = policy_v1.parameters.priority.model_copy(
        update={"contact_outcome_scores": incomplete_scores}
    )
    tampered_parameters = policy_v1.parameters.model_copy(
        update={"priority": tampered_priority}
    )
    tampered_rule_set = policy_v1.model_copy(update={"parameters": tampered_parameters})

    provider = PolicyProvider()
    provider.register(tampered_rule_set)
    provider.activate("policy-v1", clock)

    result = compute_priority(_default_input(ContactOutcome.PTP_BROKEN), provider)

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE


def test_missing_contact_outcome_score_entry_does_not_affect_other_outcomes(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> None:
    """An input that never touches the missing entry still scores normally."""
    incomplete_scores = dict(policy_v1.parameters.priority.contact_outcome_scores)
    del incomplete_scores[ContactOutcome.PTP_BROKEN]
    tampered_priority = policy_v1.parameters.priority.model_copy(
        update={"contact_outcome_scores": incomplete_scores}
    )
    tampered_parameters = policy_v1.parameters.model_copy(
        update={"priority": tampered_priority}
    )
    tampered_rule_set = policy_v1.model_copy(update={"parameters": tampered_parameters})

    provider = PolicyProvider()
    provider.register(tampered_rule_set)
    provider.activate("policy-v1", clock)

    result = compute_priority(_default_input(ContactOutcome.NO_CONTACT), provider)

    assert result.ok


def test_zero_overdue_amount_normalization_returns_policy_unavailable(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> None:
    tampered_normalization = policy_v1.parameters.priority.normalization.model_copy(
        update={"overdue_amount": Money("0.00")}
    )
    tampered_priority = policy_v1.parameters.priority.model_copy(
        update={"normalization": tampered_normalization}
    )
    tampered_parameters = policy_v1.parameters.model_copy(
        update={"priority": tampered_priority}
    )
    tampered_rule_set = policy_v1.model_copy(update={"parameters": tampered_parameters})

    provider = PolicyProvider()
    provider.register(tampered_rule_set)
    provider.activate("policy-v1", clock)

    result = compute_priority(_default_input(), provider)

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE
