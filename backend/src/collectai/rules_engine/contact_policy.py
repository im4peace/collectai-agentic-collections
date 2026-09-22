"""Deterministic contact-frequency policy (E2-S4 AC1, AC2).

Mirrors `specs/design/api-contracts.md`'s `ContactPolicyResult` schema. Two
independent checks against the active `PolicyRuleSet.parameters.contact`:

* MAX_ATTEMPTS -- too many contact attempts already made in the configured
  period.
* MIN_INTERVAL -- the last attempt is too recent, relative to the injected
  `Clock` (never wall-clock time; see `types/clock.py`).

These are simulated demo rules per BRD 13.3, not regulatory claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from collectai.config.policy.provider import PolicyProvider
from collectai.types.clock import Clock
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable


@dataclass(frozen=True, slots=True)
class ContactPolicyResult:
    """Contact-frequency policy result (api-contracts.md `ContactPolicyResult`)."""

    contact_allowed: bool
    reason_code: ReasonCode | None
    next_allowed_at: datetime | None
    attempts_in_period: int


def check_contact_policy(
    attempts_in_period: int,
    last_attempt_at: datetime | None,
    policy_provider: PolicyProvider,
    clock: Clock,
) -> ContactPolicyResult:
    """Decide whether another contact attempt is allowed right now.

    Fail-closed (CLAUDE.md "Core Engineering Principle"): if no `PolicyRuleSet`
    is active, contact is denied with `POLICY_UNAVAILABLE` rather than
    silently allowed.

    When both MAX_ATTEMPTS and MIN_INTERVAL would deny simultaneously,
    MAX_ATTEMPTS takes precedence (checked first, below) -- a single,
    deterministic reason code is always returned, never a list.
    """
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable:
        return _denied(ReasonCode.POLICY_UNAVAILABLE, None, attempts_in_period)

    contact = policy.parameters.contact
    if attempts_in_period >= contact.max_attempts:
        # No precise reopening time is specified by the contract for this
        # case (it depends on when the period's oldest attempt ages out, a
        # fact this function is not given) -- deliberately left None rather
        # than inventing unspecified precision.
        return _denied(ReasonCode.MAX_ATTEMPTS, None, attempts_in_period)

    next_allowed_at = _next_allowed_at_for_min_interval(
        last_attempt_at, contact.min_interval_hours
    )
    if next_allowed_at is not None and clock.now() < next_allowed_at:
        return _denied(ReasonCode.MIN_INTERVAL, next_allowed_at, attempts_in_period)

    return ContactPolicyResult(
        contact_allowed=True,
        reason_code=None,
        next_allowed_at=None,
        attempts_in_period=attempts_in_period,
    )


def _next_allowed_at_for_min_interval(
    last_attempt_at: datetime | None, min_interval_hours: int
) -> datetime | None:
    """`None` when the check does not apply: no prior attempt, or the
    interval is disabled (`min_interval_hours == 0`, per the contract's own
    "0 disables" note)."""
    if last_attempt_at is None or min_interval_hours == 0:
        return None
    return last_attempt_at + timedelta(hours=min_interval_hours)


def _denied(
    reason_code: ReasonCode, next_allowed_at: datetime | None, attempts_in_period: int
) -> ContactPolicyResult:
    return ContactPolicyResult(
        contact_allowed=False,
        reason_code=reason_code,
        next_allowed_at=next_allowed_at,
        attempts_in_period=attempts_in_period,
    )
