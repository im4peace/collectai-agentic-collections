"""Tests for the in-memory versioned PolicyRuleSet registry (E1-S2 AC3, AC4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import (
    PolicyProvider,
    PolicyVersionAlreadyRegisteredError,
    PolicyVersionNotFoundError,
)
from collectai.types.clock import SimulatedClock
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable


def test_get_active_raises_policy_unavailable_when_nothing_registered() -> None:
    provider = PolicyProvider()
    with pytest.raises(PolicyUnavailable) as exc_info:
        provider.get_active()
    assert exc_info.value.reason_code == ReasonCode.POLICY_UNAVAILABLE


def test_get_active_raises_policy_unavailable_when_registered_but_not_activated() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))

    with pytest.raises(PolicyUnavailable):
        provider.get_active()


def test_activate_makes_the_rule_set_available_via_get_active() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))

    activated = provider.activate("policy-v1", clock)

    assert activated.is_active is True
    assert activated.activated_at == datetime(2026, 9, 1, tzinfo=UTC)
    active = provider.get_active()
    assert active.policy_version == "policy-v1"
    assert active.is_active is True


def test_exactly_one_version_is_active_at_a_time() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()

    version_one = load_seed_policy_v1(clock)
    provider.register(version_one)
    provider.activate("policy-v1", clock)

    version_two = version_one.model_copy(
        update={
            "policy_version": "policy-v2",
            "parameters": version_one.parameters.model_copy(
                update={
                    "ptp": version_one.parameters.ptp.model_copy(
                        update={"min_amount": Money("15.00")}
                    )
                }
            ),
        }
    )
    provider.register(version_two)
    clock.advance(days=1)
    provider.activate("policy-v2", clock)

    active = provider.get_active()
    assert active.policy_version == "policy-v2"

    previous = provider.get_by_version("policy-v1")
    assert previous.is_active is False


def test_earlier_version_stays_loadable_with_original_values_after_new_version_activates() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()

    version_one = load_seed_policy_v1(clock)
    provider.register(version_one)
    provider.activate("policy-v1", clock)
    original_min_amount = version_one.parameters.ptp.min_amount

    version_two = version_one.model_copy(
        update={
            "policy_version": "policy-v2",
            "parameters": version_one.parameters.model_copy(
                update={
                    "ptp": version_one.parameters.ptp.model_copy(
                        update={"min_amount": Money("15.00")}
                    )
                }
            ),
        }
    )
    provider.register(version_two)
    provider.activate("policy-v2", clock)

    loaded_v1 = provider.get_by_version("policy-v1")
    assert loaded_v1.parameters.ptp.min_amount == original_min_amount


def test_registering_the_same_version_twice_raises_named_error() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))

    with pytest.raises(PolicyVersionAlreadyRegisteredError):
        provider.register(load_seed_policy_v1(clock))


def test_activating_unregistered_version_raises_named_error() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    provider = PolicyProvider()

    with pytest.raises(PolicyVersionNotFoundError):
        provider.activate("policy-v99", clock)


def test_get_by_version_for_unregistered_version_raises_named_error() -> None:
    provider = PolicyProvider()
    with pytest.raises(PolicyVersionNotFoundError):
        provider.get_by_version("policy-v99")
