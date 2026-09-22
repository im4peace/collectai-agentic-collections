"""E2-S4 AC1, AC2: contact-frequency policy (MAX_ATTEMPTS, MIN_INTERVAL).

Uses the seeded `policy-v1` contact parameters (`contact.max_attempts=3`,
`contact.min_interval_hours=24`) via the shared `active_policy_provider`
fixture in `conftest.py`. All interval checks are relative to the injected
`SimulatedClock`, never wall-clock time.
"""

from __future__ import annotations

from datetime import timedelta

from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.rules_engine.contact_policy import check_contact_policy
from collectai.types.clock import SimulatedClock
from collectai.types.reason_codes import ReasonCode


def test_contact_allowed_one_attempt_below_configured_maximum(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    result = check_contact_policy(
        attempts_in_period=2, last_attempt_at=None, policy_provider=active_policy_provider,
        clock=clock,
    )

    assert result.contact_allowed is True
    assert result.reason_code is None
    assert result.attempts_in_period == 2


def test_contact_denied_max_attempts_when_attempts_reach_configured_maximum(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    result = check_contact_policy(
        attempts_in_period=3, last_attempt_at=None, policy_provider=active_policy_provider,
        clock=clock,
    )

    assert result.contact_allowed is False
    assert result.reason_code == ReasonCode.MAX_ATTEMPTS
    assert result.next_allowed_at is None
    assert result.attempts_in_period == 3


def test_contact_denied_min_interval_when_last_attempt_within_configured_interval(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    last_attempt_at = clock.now() - timedelta(hours=23, minutes=59)

    result = check_contact_policy(
        attempts_in_period=0, last_attempt_at=last_attempt_at,
        policy_provider=active_policy_provider, clock=clock,
    )

    assert result.contact_allowed is False
    assert result.reason_code == ReasonCode.MIN_INTERVAL
    assert result.next_allowed_at == last_attempt_at + timedelta(hours=24)
    assert result.attempts_in_period == 0


def test_contact_allowed_once_configured_interval_has_fully_elapsed(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    last_attempt_at = clock.now() - timedelta(hours=24)

    result = check_contact_policy(
        attempts_in_period=0, last_attempt_at=last_attempt_at,
        policy_provider=active_policy_provider, clock=clock,
    )

    assert result.contact_allowed is True
    assert result.reason_code is None
    assert result.next_allowed_at is None


def test_min_interval_hours_zero_disables_the_check(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> None:
    tampered_contact = policy_v1.parameters.contact.model_copy(update={"min_interval_hours": 0})
    tampered_parameters = policy_v1.parameters.model_copy(update={"contact": tampered_contact})
    tampered_rule_set = policy_v1.model_copy(update={"parameters": tampered_parameters})
    provider = PolicyProvider()
    provider.register(tampered_rule_set)
    provider.activate("policy-v1", clock)
    last_attempt_at = clock.now()  # the most recent possible attempt: zero elapsed time

    result = check_contact_policy(
        attempts_in_period=0, last_attempt_at=last_attempt_at, policy_provider=provider,
        clock=clock,
    )

    assert result.contact_allowed is True
    assert result.reason_code is None


def test_no_prior_attempt_never_triggers_min_interval(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    result = check_contact_policy(
        attempts_in_period=0, last_attempt_at=None, policy_provider=active_policy_provider,
        clock=clock,
    )

    assert result.contact_allowed is True
    assert result.reason_code is None


def test_max_attempts_takes_precedence_over_min_interval_when_both_would_deny(
    active_policy_provider: PolicyProvider, clock: SimulatedClock
) -> None:
    last_attempt_at = clock.now() - timedelta(minutes=1)  # also within min_interval_hours=24

    result = check_contact_policy(
        attempts_in_period=3, last_attempt_at=last_attempt_at,
        policy_provider=active_policy_provider, clock=clock,
    )

    assert result.contact_allowed is False
    assert result.reason_code == ReasonCode.MAX_ATTEMPTS
    assert result.next_allowed_at is None


def test_no_active_policy_fails_closed_and_denies_contact(clock: SimulatedClock) -> None:
    provider = PolicyProvider()

    result = check_contact_policy(
        attempts_in_period=0, last_attempt_at=None, policy_provider=provider, clock=clock,
    )

    assert result.contact_allowed is False
    assert result.reason_code == ReasonCode.POLICY_UNAVAILABLE
