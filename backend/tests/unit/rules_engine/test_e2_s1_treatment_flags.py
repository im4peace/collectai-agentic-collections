"""E2-S1 AC4: human_treatment / automated_treatment_suppressed flags.

True when any of active dispute, active hardship or open escalation applies;
false only when none apply. This is a deliberately narrow slice of the full
suppression engine (E2-S4 replaces the computation, not the field shape).
"""

from __future__ import annotations

import pytest

from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.priority import PriorityInput, compute_priority
from collectai.types.money import Money


def _base_input(
    *, has_active_dispute: bool, has_active_hardship: bool, has_open_escalation: bool
) -> PriorityInput:
    return PriorityInput(
        dpd=10,
        overdue_amount=Money("100.00"),
        broken_ptp_count=0,
        recent_contact_outcome=None,
        has_active_dispute=has_active_dispute,
        has_active_hardship=has_active_hardship,
        has_open_escalation=has_open_escalation,
    )


def test_no_flags_set_when_no_suppression_condition_applies(
    active_policy_provider: PolicyProvider,
) -> None:
    priority_input = _base_input(
        has_active_dispute=False, has_active_hardship=False, has_open_escalation=False
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.human_treatment is False
    assert result.value.automated_treatment_suppressed is False


@pytest.mark.parametrize(
    ("has_active_dispute", "has_active_hardship", "has_open_escalation"),
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, True),
    ],
)
def test_flags_set_true_when_any_suppression_condition_applies(
    active_policy_provider: PolicyProvider,
    has_active_dispute: bool,
    has_active_hardship: bool,
    has_open_escalation: bool,
) -> None:
    priority_input = _base_input(
        has_active_dispute=has_active_dispute,
        has_active_hardship=has_active_hardship,
        has_open_escalation=has_open_escalation,
    )

    result = compute_priority(priority_input, active_policy_provider)

    assert result.value is not None
    assert result.value.human_treatment is True
    assert result.value.automated_treatment_suppressed is True
