"""E2-S4 AC3, AC4: treatment-suppression engine.

Uses the seeded `policy-v1` suppression scopes (`dispute_scope=ITEM`,
`hardship_scope=ACCOUNT`, `vulnerable_scope=ACCOUNT`) via the `policy_v1`
fixture in `conftest.py`.
"""

from __future__ import annotations

from collectai.config.policy.models import PolicyRuleSet
from collectai.rules_engine.suppression import (
    SuppressionEntry,
    SuppressionInput,
    evaluate_suppression,
)
from collectai.types.enums import SuppressionScope, SuppressionSource


def _no_suppression_input() -> SuppressionInput:
    return SuppressionInput(
        has_open_escalation=False,
        escalation_case_id=None,
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[],
    )


def test_no_suppression_conditions_allows_automated_treatment(policy_v1: PolicyRuleSet) -> None:
    result = evaluate_suppression(_no_suppression_input(), policy_v1)

    assert result.human_treatment is False
    assert result.automated_treatment_suppressed is False
    assert result.suppressions == []


def test_dispute_on_one_item_suppresses_only_that_item(policy_v1: PolicyRuleSet) -> None:
    """AC3: an active dispute on an item suppresses automated recommendations
    for that item only; other items on the account remain eligible."""
    suppression_input = SuppressionInput(
        has_open_escalation=False,
        escalation_case_id=None,
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[("dsp_1a2b3c", "itm_A")],
    )

    disputed_item_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_A")
    other_item_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_B")

    assert disputed_item_result.automated_treatment_suppressed is True
    assert disputed_item_result.human_treatment is True
    assert other_item_result.automated_treatment_suppressed is False
    assert other_item_result.human_treatment is False
    # Both queries see the same active-suppression list; only the applied
    # flags differ by the queried item.
    assert disputed_item_result.suppressions == other_item_result.suppressions
    assert disputed_item_result.suppressions == [
        _entry(SuppressionSource.DISPUTE, "dsp_1a2b3c", SuppressionScope.ITEM, "itm_A")
    ]


def test_dispute_with_no_item_id_suppresses_every_item(policy_v1: PolicyRuleSet) -> None:
    """A dispute with no `item_id` of its own covers the whole overdue
    amount (data-models.md `Dispute`), so it suppresses any queried item."""
    suppression_input = SuppressionInput(
        has_open_escalation=False,
        escalation_case_id=None,
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[("dsp_wholebalance", None)],
    )

    item_a_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_A")
    item_b_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_B")

    assert item_a_result.automated_treatment_suppressed is True
    assert item_b_result.automated_treatment_suppressed is True


def test_active_hardship_suppresses_automated_treatment_account_wide(
    policy_v1: PolicyRuleSet,
) -> None:
    """AC4: active hardship suppresses all automated treatment for the
    account, regardless of which item (or none) is queried."""
    suppression_input = SuppressionInput(
        has_open_escalation=False,
        escalation_case_id=None,
        has_active_hardship=True,
        hardship_case_id="hsc_7f8e9d",
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[],
    )

    account_level_result = evaluate_suppression(suppression_input, policy_v1)
    item_scoped_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_anything")

    assert account_level_result.automated_treatment_suppressed is True
    assert account_level_result.human_treatment is True
    assert item_scoped_result.automated_treatment_suppressed is True
    assert account_level_result.suppressions == [
        _entry(SuppressionSource.HARDSHIP, "hsc_7f8e9d", SuppressionScope.ACCOUNT, None)
    ]


def test_vulnerable_customer_flag_suppresses_automated_treatment_account_wide(
    policy_v1: PolicyRuleSet,
) -> None:
    """AC4: a vulnerable-customer flag suppresses all automated treatment
    for the account, regardless of which item (or none) is queried."""
    suppression_input = SuppressionInput(
        has_open_escalation=False,
        escalation_case_id=None,
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=True,
        customer_id="cus_4d5e6f",
        open_disputes=[],
    )

    account_level_result = evaluate_suppression(suppression_input, policy_v1)
    item_scoped_result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_anything")

    assert account_level_result.automated_treatment_suppressed is True
    assert item_scoped_result.automated_treatment_suppressed is True
    assert account_level_result.suppressions == [
        _entry(SuppressionSource.VULNERABLE, "cus_4d5e6f", SuppressionScope.ACCOUNT, None)
    ]


def test_open_escalation_suppresses_automated_treatment_account_wide(
    policy_v1: PolicyRuleSet,
) -> None:
    """Open escalation is hardcoded ACCOUNT scope (data-models.md 4.4), not a
    policy parameter."""
    suppression_input = SuppressionInput(
        has_open_escalation=True,
        escalation_case_id="esc_2a3b4c",
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[],
    )

    result = evaluate_suppression(suppression_input, policy_v1, item_id="itm_anything")

    assert result.automated_treatment_suppressed is True
    assert result.suppressions == [
        _entry(SuppressionSource.ESCALATION, "esc_2a3b4c", SuppressionScope.ACCOUNT, None)
    ]


def test_missing_source_id_falls_back_to_placeholder_when_flag_is_true(
    policy_v1: PolicyRuleSet,
) -> None:
    """Defensive fallback for a caller (e.g. `rules_engine/priority.py`'s
    narrower seam) that sets a flag true without a real case id."""
    suppression_input = SuppressionInput(
        has_open_escalation=True,
        escalation_case_id=None,
        has_active_hardship=False,
        hardship_case_id=None,
        is_vulnerable_customer=False,
        customer_id=None,
        open_disputes=[],
    )

    result = evaluate_suppression(suppression_input, policy_v1)

    assert result.suppressions[0].source_id == "unknown"


def _entry(
    source_type: SuppressionSource,
    source_id: str,
    scope: SuppressionScope,
    item_id: str | None,
) -> SuppressionEntry:
    return SuppressionEntry(
        source_type=source_type, source_id=source_id, scope=scope, item_id=item_id
    )
