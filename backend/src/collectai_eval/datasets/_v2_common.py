"""Shared shape and helpers for the `eval-ds-v2` case banks (E10-S1 AC6).

Each bank module (`_v2_sensitive_a`, `_v2_sensitive_b`, `_v2_general`) holds hand-written
messages plus their labels, per `EVAL_DS_V2_LABELLING_RUBRIC.md`. `_build_eval_ds_v2.py`
assigns the `case_id`s in bank order, so a case's id is stable as long as the banks are only
appended to. Nothing here calls a model: the messages are drafted text, not model output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewCase:
    category: str
    message: str
    expected_intent: str
    vulnerability_category: str | None = None
    special_request: str = "NONE"
    escalation_reason: str | None = None


def cases(
    category: str,
    intent: str,
    messages: Sequence[str],
    *,
    special_request: str = "NONE",
    escalation_reason: str | None = None,
) -> list[NewCase]:
    """Every message gets the same labels."""
    return [
        NewCase(
            category=category,
            message=message,
            expected_intent=intent,
            special_request=special_request,
            escalation_reason=escalation_reason,
        )
        for message in messages
    ]


def vulnerable(
    vulnerability_category: str, intent: str, messages: Sequence[str]
) -> list[NewCase]:
    """`VULNERABLE_CUSTOMER` safety-set cases: the signal is set, so the reason is derived."""
    return [
        NewCase(
            category="VULNERABLE_CUSTOMER",
            message=message,
            expected_intent=intent,
            vulnerability_category=vulnerability_category,
            escalation_reason="VULNERABLE_CUSTOMER",
        )
        for message in messages
    ]
