"""Shared vocabulary for deterministic rules-engine outcomes.

Every rules-engine service in later stories returns results through these
three thin types: a typed failure (`RuleFailure`), a generic success/failure
wrapper (`RuleResult`), and the fixed fail-closed signal (`PolicyUnavailable`)
required when there is no valid active `PolicyRuleSet`
(specs/policy-ruleset-contract.md section 1). This module intentionally does
not define any business-specific fields; those belong to each rule story.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from collectai.types.reason_codes import ReasonCode

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RuleFailure:
    """A rejected or ineligible rule outcome, with a stable reason code."""

    reason_code: ReasonCode
    message: str
    details: dict[str, object] | None = None


class PolicyUnavailable(Exception):
    """Raised by a rules service when there is no valid active PolicyRuleSet.

    Per the PolicyRuleSet contract, this is fail-closed: the caller grants no
    eligibility, offers no options and produces no score.
    """

    def __init__(self, message: str = "No valid active PolicyRuleSet is available.") -> None:
        self.reason_code = ReasonCode.POLICY_UNAVAILABLE
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RuleResult(Generic[T]):
    """A rule outcome that is either a success value or a `RuleFailure`."""

    value: T | None
    failure: RuleFailure | None

    @property
    def ok(self) -> bool:
        return self.failure is None

    @classmethod
    def success(cls, value: T) -> RuleResult[T]:
        return cls(value=value, failure=None)

    @classmethod
    def fail(cls, failure: RuleFailure) -> RuleResult[T]:
        return cls(value=None, failure=failure)
