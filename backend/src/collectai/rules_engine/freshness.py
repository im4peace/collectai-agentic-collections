"""Deterministic snapshot freshness check (E2-S5 AC1, AC2, AC3).

`check_freshness` is a pure function over already-fetched inputs: it never
touches persistence itself. A caller (`domain_services.snapshot_service`)
fetches the current `DelinquencyRecord` and passes it straight through; this
module only ever *compares* values it is handed.

AC2/AC3 wording resolution
---------------------------
AC2 says "a stale snapshot **or** a version mismatch causes the consequential
action to be refused with reason STALE_DATA", while AC3 separately wants an
UNKNOWN state with AMBIGUOUS_VALIDATION for when "freshness cannot be
established". Read literally these overlap for the version-mismatch case.
This module resolves the overlap as follows, and every branch below is
covered by a named test in `tests/unit/rules_engine/test_e2_s5_freshness.py`:

- **Missing `as_of`** -> `UNKNOWN` / `AMBIGUOUS_VALIDATION`. A snapshot with
  no timestamp is never treated as fresh (fail closed); there is nothing to
  measure an age against, so freshness is strictly unknowable, not merely old.
- **Version mismatch** (`snapshot_version != current_record.record_version`)
  -> `UNKNOWN` / `AMBIGUOUS_VALIDATION`. A version mismatch means the caller's
  snapshot describes a record state that no longer exists -- freshness
  literally cannot be established against a record that has since changed,
  which is exactly AC3's "freshness cannot be established" condition. This is
  a materially different failure than mere staleness (AC1 explicitly lists
  UNKNOWN as its own third status, not a sub-case of STALE).
- **Aged, but version-matching** snapshot (age strictly greater than
  `policy.parameters.freshness.max_snapshot_age_minutes`) -> `STALE` /
  `STALE_DATA`. This is the one case where the record is unambiguously the
  same one, just measured too long ago.

In every branch the consequential action is still refused (AC2's outcome
applies uniformly); only the reported `status`/`reason_code` differs by
branch, and callers (`domain_services.snapshot_service`) treat any non-FRESH
status as a failure with no state change, satisfying AC5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from collectai.config.policy.models import PolicyRuleSet
from collectai.types.clock import Clock
from collectai.types.enums import Freshness
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.reason_codes import ReasonCode


@dataclass(frozen=True, slots=True)
class FreshnessCheckResult:
    """Outcome of comparing a caller's snapshot to the current record.

    `current_record` is always populated (never fetched by this module --
    see the module docstring) so a caller that receives a non-FRESH result
    already has the refreshed context it needs (AC2).
    """

    status: Freshness
    reason_code: ReasonCode | None
    current_record: DelinquencyRecord


def check_freshness(
    *,
    snapshot_as_of: datetime | None,
    snapshot_version: int,
    current_record: DelinquencyRecord,
    policy: PolicyRuleSet,
    clock: Clock,
) -> FreshnessCheckResult:
    """Compare a snapshot's `as_of`/version against `current_record` (AC1)."""
    if snapshot_as_of is None:
        return _unknown(current_record)
    if snapshot_version != current_record.record_version:
        return _unknown(current_record)
    if _is_aged_past_threshold(snapshot_as_of, policy, clock):
        return FreshnessCheckResult(
            status=Freshness.STALE,
            reason_code=ReasonCode.STALE_DATA,
            current_record=current_record,
        )
    return FreshnessCheckResult(
        status=Freshness.FRESH, reason_code=None, current_record=current_record
    )


def _unknown(current_record: DelinquencyRecord) -> FreshnessCheckResult:
    return FreshnessCheckResult(
        status=Freshness.UNKNOWN,
        reason_code=ReasonCode.AMBIGUOUS_VALIDATION,
        current_record=current_record,
    )


def _is_aged_past_threshold(snapshot_as_of: datetime, policy: PolicyRuleSet, clock: Clock) -> bool:
    max_age = timedelta(minutes=policy.parameters.freshness.max_snapshot_age_minutes)
    age = clock.now() - snapshot_as_of
    return age > max_age
