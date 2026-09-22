"""Shared fixtures for E2-S1 Collections Priority service tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.types.clock import SimulatedClock


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))


@pytest.fixture
def policy_v1(clock: SimulatedClock) -> PolicyRuleSet:
    return load_seed_policy_v1(clock)


@pytest.fixture
def active_policy_provider(
    policy_v1: PolicyRuleSet, clock: SimulatedClock
) -> PolicyProvider:
    """A `PolicyProvider` with the seeded `policy-v1` rule set active."""
    provider = PolicyProvider()
    provider.register(policy_v1)
    provider.activate("policy-v1", clock)
    return provider
