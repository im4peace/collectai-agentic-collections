"""In-memory versioned `PolicyRuleSet` registry.

Fail-closed contract (specs/policy-ruleset-contract.md section 1, AC3): calling
`get_active()` when no version is currently active — including before any
rule set has ever been registered — raises
`collectai.types.results.PolicyUnavailable` (carrying
`ReasonCode.POLICY_UNAVAILABLE`). Every rules-engine service in later stories
must call `get_active()` (never cache a rule set itself) so this fail-closed
behavior is enforced in exactly one place.

Immutability: `PolicyRuleSet` instances are frozen Pydantic models. Activating
a version never mutates an existing instance; it stores a new
`model_copy(update=...)` under the same registry key. An earlier version stays
registered, unmutated, and readable via `get_by_version` after a newer version
becomes active (AC4).
"""

from __future__ import annotations

import logging

from collectai.config.policy.models import PolicyRuleSet
from collectai.types.clock import Clock
from collectai.types.results import PolicyUnavailable

logger = logging.getLogger(__name__)


class PolicyVersionAlreadyRegisteredError(Exception):
    """Raised when a version is registered twice, preserving per-version immutability."""

    def __init__(self, policy_version: str) -> None:
        self.policy_version = policy_version
        super().__init__(f"PolicyRuleSet version already registered: {policy_version!r}")


class PolicyVersionNotFoundError(Exception):
    """Raised when a requested policy version has never been registered."""

    def __init__(self, policy_version: str) -> None:
        self.policy_version = policy_version
        super().__init__(f"No PolicyRuleSet registered for version: {policy_version!r}")


class PolicyProvider:
    """Register, activate and read versioned `PolicyRuleSet`s.

    At most one version is active at a time. `get_active()` is the fail-closed
    entry point every rules service must use.
    """

    def __init__(self) -> None:
        self._by_version: dict[str, PolicyRuleSet] = {}
        self._active_version: str | None = None

    def register(self, rule_set: PolicyRuleSet) -> None:
        """Add a new, not-yet-active `PolicyRuleSet` to the registry."""
        if rule_set.policy_version in self._by_version:
            raise PolicyVersionAlreadyRegisteredError(rule_set.policy_version)
        self._by_version[rule_set.policy_version] = rule_set
        logger.info(
            "Policy rule set registered",
            extra={"policy_version": rule_set.policy_version},
        )

    def activate(self, policy_version: str, clock: Clock) -> PolicyRuleSet:
        """Make `policy_version` the sole active version; return the activated copy."""
        if policy_version not in self._by_version:
            raise PolicyVersionNotFoundError(policy_version)

        if self._active_version is not None and self._active_version != policy_version:
            self._deactivate(self._active_version)

        activated = self._by_version[policy_version].model_copy(
            update={"is_active": True, "activated_at": clock.now()}
        )
        self._by_version[policy_version] = activated
        self._active_version = policy_version
        logger.info(
            "Policy rule set activated",
            extra={"policy_version": policy_version, "activated_at": activated.activated_at},
        )
        return activated

    def get_active(self) -> PolicyRuleSet:
        """Return the currently active `PolicyRuleSet`.

        Raises `PolicyUnavailable` (fail closed) when no version is active.
        """
        if self._active_version is None:
            logger.warning("No active PolicyRuleSet is available; failing closed.")
            raise PolicyUnavailable()
        return self._by_version[self._active_version]

    def get_by_version(self, policy_version: str) -> PolicyRuleSet:
        """Return a specific version, active or not, read-only, with original values."""
        try:
            return self._by_version[policy_version]
        except KeyError as exc:
            raise PolicyVersionNotFoundError(policy_version) from exc

    def _deactivate(self, policy_version: str) -> None:
        self._by_version[policy_version] = self._by_version[policy_version].model_copy(
            update={"is_active": False}
        )
