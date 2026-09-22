"""Escalation routing service (E2-S6).

Decides the review queue, reviewer role and priority for an escalation
reason. Per `specs/policy-ruleset-contract.md` and `CLAUDE.md`'s
human-in-the-loop rule, this module is the *only* place a queue or
reviewer role is ever decided -- the LLM proposes only a reason, never a
destination, and `route_escalation` never accepts a `queue` or
`reviewer_role` parameter (AC3).

DISTINCTIVE BEHAVIOR -- do not "fix" this to match sibling rules-engine
services: every other deterministic rule in this package (priority, ptp
validation, arrangement eligibility, ...) returns `RuleResult[T]` and a
`RuleFailure(reason_code=POLICY_UNAVAILABLE)` -- i.e. no usable value --
when there is no active `PolicyRuleSet`. This service is the exception
(AC5): routing an escalation to a human queue *is itself* the fail-closed
safety net. If routing produced nothing on a policy outage, the escalation
would be lost entirely, defeating the point of having a routing service at
all. So `route_escalation` always returns a plain, complete `RoutingResult`
-- never wrapped in `RuleResult`, never `None`, never raising -- falling
back to a hardcoded destination (`ReviewQueue.COLLECTIONS_REVIEW` /
`ReviewerRole.COLLECTIONS_OFFICER`, literal constants, never read from the
unavailable policy) with `policy_version=None` and
`flags=["POLICY_UNAVAILABLE"]` when no policy is active.

Two independent, non-overlapping degraded paths exist:
  - Policy unavailable (AC5): hardcoded fallback destination, regardless of
    whether `reason` was recognized. `flags=["POLICY_UNAVAILABLE"]`.
  - Policy available but `reason` unrecognized or missing (AC2): the
    *policy's own* `routing.fallback` destination (not the AC5 hardcoded
    one -- policy is readable here, so its configured fallback is used).
    `flags=["reason_unrecognized"]`.

`RoutingResult.reason` keeps the normalized `EscalationReason` that was
actually used to look up a destination (including under AC5, when the
input reason was recognized but policy was unavailable, for traceability),
or `None` when the input reason itself was not a valid `EscalationReason`
member.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from collectai.config.policy.models import RoutingParameters
from collectai.config.policy.provider import PolicyProvider
from collectai.types.enums import EscalationPriority, EscalationReason, ReviewerRole, ReviewQueue
from collectai.types.results import PolicyUnavailable

# AC5: hardcoded fail-closed destination, deliberately not read from the
# (by definition unreadable) unavailable policy.
_POLICY_UNAVAILABLE_QUEUE: Final = ReviewQueue.COLLECTIONS_REVIEW
_POLICY_UNAVAILABLE_REVIEWER_ROLE: Final = ReviewerRole.COLLECTIONS_OFFICER

# Priority is not specified by the contract for either degraded path.
# NORMAL is chosen deliberately for both: neither "policy is down" nor
# "the reason string is unrecognized" gives us any signal about the
# customer's actual risk or urgency, so we do not want to manufacture a
# false sense of elevated severity. A human still reviews it promptly
# because it lands in a real queue either way; NORMAL just avoids
# artificially crowding the ELEVATED/URGENT lanes that are reserved for
# reasons the policy explicitly flags as more severe (e.g.
# VULNERABLE_CUSTOMER, HIGH_RISK_COMPLIANCE).
_POLICY_UNAVAILABLE_PRIORITY: Final = EscalationPriority.NORMAL
_UNRECOGNIZED_REASON_PRIORITY: Final = EscalationPriority.NORMAL

_FLAG_POLICY_UNAVAILABLE: Final = "POLICY_UNAVAILABLE"
_FLAG_REASON_UNRECOGNIZED: Final = "reason_unrecognized"


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """The destination and priority decided for one escalation.

    Always a complete, valid result -- see the module docstring for why
    this is never wrapped in `RuleResult` unlike sibling rules-engine
    services.
    """

    reason: EscalationReason | None
    queue: ReviewQueue
    reviewer_role: ReviewerRole
    priority: EscalationPriority
    policy_version: str | None
    flags: list[str]


def route_escalation(
    reason: EscalationReason | str | None, policy_provider: PolicyProvider
) -> RoutingResult:
    """Decide the queue, reviewer role and priority for `reason`.

    Deliberately takes only `reason` and `policy_provider` -- never a
    `queue` or `reviewer_role` (AC3): this function is the single place a
    destination is decided, not a place one is confirmed.
    """
    try:
        rule_set = policy_provider.get_active()
    except PolicyUnavailable:
        return _route_with_policy_unavailable(reason)

    normalized_reason = _normalize_reason(reason)
    routing = rule_set.parameters.routing
    if normalized_reason is None:
        return _route_unrecognized_reason(routing, rule_set.policy_version)
    return _route_recognized_reason(normalized_reason, routing, rule_set.policy_version)


def _normalize_reason(reason: EscalationReason | str | None) -> EscalationReason | None:
    """Parse `reason` into a valid `EscalationReason`, or `None` if it is not one."""
    if isinstance(reason, EscalationReason):
        return reason
    if reason is None:
        return None
    try:
        return EscalationReason(reason)
    except ValueError:
        return None


def _route_with_policy_unavailable(reason: EscalationReason | str | None) -> RoutingResult:
    return RoutingResult(
        reason=_normalize_reason(reason),
        queue=_POLICY_UNAVAILABLE_QUEUE,
        reviewer_role=_POLICY_UNAVAILABLE_REVIEWER_ROLE,
        priority=_POLICY_UNAVAILABLE_PRIORITY,
        policy_version=None,
        flags=[_FLAG_POLICY_UNAVAILABLE],
    )


def _route_unrecognized_reason(
    routing: RoutingParameters, policy_version: str
) -> RoutingResult:
    return RoutingResult(
        reason=None,
        queue=routing.fallback.queue,
        reviewer_role=routing.fallback.reviewer_role,
        priority=_UNRECOGNIZED_REASON_PRIORITY,
        policy_version=policy_version,
        flags=[_FLAG_REASON_UNRECOGNIZED],
    )


def _route_recognized_reason(
    reason: EscalationReason, routing: RoutingParameters, policy_version: str
) -> RoutingResult:
    # Defensive: `config.policy.validator` guarantees `routing.table` covers
    # every `EscalationReason` before a rule set is ever registered, but
    # this service never crashes if that guarantee is somehow violated --
    # it falls back to the policy's own fallback destination instead.
    destination = routing.table.get(reason, routing.fallback)
    priority = routing.priority_by_reason.get(reason, _UNRECOGNIZED_REASON_PRIORITY)
    return RoutingResult(
        reason=reason,
        queue=destination.queue,
        reviewer_role=destination.reviewer_role,
        priority=priority,
        policy_version=policy_version,
        flags=[],
    )
