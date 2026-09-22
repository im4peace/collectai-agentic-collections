"""Deterministic treatment-suppression engine (E2-S4 AC3, AC4).

Mirrors `specs/design/api-contracts.md`'s `TreatmentBlock`/`SuppressionEntry`
schemas and implements `specs/design/data-models.md` section 4.4 "Treatment
suppression (derived)": four independent conditions, each contributing at
most one `SuppressionEntry` when true --

1. open escalation -- always `SuppressionScope.ACCOUNT` (hardcoded per
   section 4.4's own text; there is no `escalation_scope` policy parameter).
2. active hardship -- scope from `policy.suppression.hardship_scope`.
3. vulnerable customer -- scope from `policy.suppression.vulnerable_scope`.
4. open dispute -- scope from `policy.suppression.dispute_scope`; a dispute
   with no `item_id` of its own still gets `item_id=None` on its entry (it
   covers "the whole overdue amount" per data-models.md's `Dispute` entity).

Release boundary: per section 4.4, a suppression clears only through a human
decision (setting `release_suppression` or resolving the dispute). This
module never re-evaluates that -- it trusts `SuppressionInput`'s booleans as
already-accurate, human-controlled facts supplied by the caller (a future
`domain_services` story). Building the release mechanism itself is out of
scope for this story.

These are simulated demo rules per BRD 13.3, not regulatory claims.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectai.config.policy.models import PolicyRuleSet
from collectai.types.enums import SuppressionScope, SuppressionSource

_UNKNOWN_SOURCE_ID = "unknown"


@dataclass(frozen=True, slots=True)
class SuppressionInput:
    """Already-resolved suppression facts for one account.

    Mirrors `PriorityInput`'s pattern (`rules_engine/priority.py`): a future
    `domain_services` story reads these from persistence; this service only
    ever receives already-resolved values, never a DB handle.

    `open_disputes` is `(dispute_id, item_id_or_none)` per open dispute; a
    `None` item id means the dispute covers the whole overdue amount.
    """

    has_open_escalation: bool
    escalation_case_id: str | None
    has_active_hardship: bool
    hardship_case_id: str | None
    is_vulnerable_customer: bool
    customer_id: str | None
    open_disputes: list[tuple[str, str | None]]


@dataclass(frozen=True, slots=True)
class SuppressionEntry:
    """Why treatment is suppressed (api-contracts.md `SuppressionEntry`)."""

    source_type: SuppressionSource
    source_id: str
    scope: SuppressionScope
    item_id: str | None


@dataclass(frozen=True, slots=True)
class TreatmentBlock:
    """Treatment suppression state (api-contracts.md `TreatmentBlock`)."""

    human_treatment: bool
    automated_treatment_suppressed: bool
    suppressions: list[SuppressionEntry]


def evaluate_suppression(
    suppression_input: SuppressionInput,
    policy: PolicyRuleSet,
    *,
    item_id: str | None = None,
) -> TreatmentBlock:
    """Derive the treatment-suppression state for an account, or one of its
    items when `item_id` is given.

    `suppressions` always lists every currently active suppression source for
    the account, regardless of `item_id`; `human_treatment` and
    `automated_treatment_suppressed` (kept equal, per how E2-S1's
    `PriorityResult` already pairs them) reflect only whether at least one of
    those entries applies to the queried scope (AC3, AC4).
    """
    entries = _collect_entries(suppression_input, policy)
    applies = any(_applies_to_query(entry, item_id) for entry in entries)
    return TreatmentBlock(
        human_treatment=applies,
        automated_treatment_suppressed=applies,
        suppressions=entries,
    )


def _collect_entries(
    suppression_input: SuppressionInput, policy: PolicyRuleSet
) -> list[SuppressionEntry]:
    suppression_params = policy.parameters.suppression
    return [
        *_escalation_entries(suppression_input),
        *_hardship_entries(suppression_input, suppression_params.hardship_scope),
        *_vulnerable_entries(suppression_input, suppression_params.vulnerable_scope),
        *_dispute_entries(suppression_input, suppression_params.dispute_scope),
    ]


def _escalation_entries(suppression_input: SuppressionInput) -> list[SuppressionEntry]:
    if not suppression_input.has_open_escalation:
        return []
    return [
        SuppressionEntry(
            source_type=SuppressionSource.ESCALATION,
            source_id=_resolve_source_id(suppression_input.escalation_case_id),
            scope=SuppressionScope.ACCOUNT,
            item_id=None,
        )
    ]


def _hardship_entries(
    suppression_input: SuppressionInput, hardship_scope: SuppressionScope
) -> list[SuppressionEntry]:
    if not suppression_input.has_active_hardship:
        return []
    return [
        SuppressionEntry(
            source_type=SuppressionSource.HARDSHIP,
            source_id=_resolve_source_id(suppression_input.hardship_case_id),
            scope=hardship_scope,
            item_id=None,
        )
    ]


def _vulnerable_entries(
    suppression_input: SuppressionInput, vulnerable_scope: SuppressionScope
) -> list[SuppressionEntry]:
    if not suppression_input.is_vulnerable_customer:
        return []
    return [
        SuppressionEntry(
            source_type=SuppressionSource.VULNERABLE,
            source_id=_resolve_source_id(suppression_input.customer_id),
            scope=vulnerable_scope,
            item_id=None,
        )
    ]


def _dispute_entries(
    suppression_input: SuppressionInput, dispute_scope: SuppressionScope
) -> list[SuppressionEntry]:
    return [
        SuppressionEntry(
            source_type=SuppressionSource.DISPUTE,
            source_id=dispute_id,
            scope=dispute_scope,
            item_id=disputed_item_id,
        )
        for dispute_id, disputed_item_id in suppression_input.open_disputes
    ]


def _resolve_source_id(explicit_id: str | None) -> str:
    """Callers are expected to supply a real case/customer id whenever the
    corresponding flag is true; this is a defensive fallback only (e.g. for
    `rules_engine/priority.py`'s narrower `PriorityInput`, which does not
    carry case ids at all)."""
    return explicit_id if explicit_id is not None else _UNKNOWN_SOURCE_ID


def _applies_to_query(entry: SuppressionEntry, item_id: str | None) -> bool:
    """Whether `entry` suppresses the queried scope.

    ACCOUNT-scope entries always apply. ITEM-scope entries apply when no
    `item_id` was queried (account-level evaluation: any entry at all
    suppresses), or when the entry's own `item_id` is `None` (covers the
    whole overdue amount) or matches the queried `item_id`.
    """
    if entry.scope is SuppressionScope.ACCOUNT:
        return True
    if item_id is None:
        return True
    return entry.item_id is None or entry.item_id == item_id
