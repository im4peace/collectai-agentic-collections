"""Deterministic internal-consistency check for a `DelinquencyRecord` (E2-S5 AC4).

Per data-models.md's own note on `delinquency_record`: bucket-vs-dpd and
`overdue_amount <= outstanding_balance` are NOT database checks -- they are
enforced here, by the rules engine, so the refusal path stays testable end
to end. `check_consistency` mirrors `api-contracts.md`'s `RecordCheck` shape
(`consistent: bool`, `reason_code: str | None`): a single flat result, not a
list of per-violation codes. `violations` is an additive, optional field for
internal logging detail only -- it is not part of the `RecordCheck` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from collectai.types.enums import Bucket
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.reason_codes import ReasonCode

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class RecordCheck:
    """Internal-consistency check result (api-contracts.md `RecordCheck`)."""

    consistent: bool
    reason_code: ReasonCode | None
    violations: tuple[str, ...] = field(default=())


def check_consistency(record: DelinquencyRecord) -> RecordCheck:
    """Refuse a `DelinquencyRecord` whose fields contradict each other (AC4)."""
    violations = _collect_violations(record)
    if not violations:
        return RecordCheck(consistent=True, reason_code=None)
    return RecordCheck(
        consistent=False,
        reason_code=ReasonCode.INCONSISTENT_RECORD,
        violations=tuple(violations),
    )


def _collect_violations(record: DelinquencyRecord) -> list[str]:
    violations: list[str] = []
    if record.bucket != _expected_bucket(record.dpd):
        violations.append("bucket_does_not_match_dpd")
    if record.overdue_amount.amount < _ZERO:
        # Defence in depth: Money.__init__ already rejects a negative amount
        # unconditionally, so this branch is unreachable through any public
        # construction path today (see the E2-S5 test module docstring).
        violations.append("overdue_amount_negative")
    if record.overdue_amount > record.outstanding_balance:
        violations.append("overdue_amount_exceeds_outstanding_balance")
    return violations


def _expected_bucket(dpd: int) -> Bucket:
    """Map `dpd` to its required `Bucket` (api-contracts.md enum ranges)."""
    if dpd == 0:
        return Bucket.CURRENT
    if dpd <= 29:
        return Bucket.DPD_1_29
    if dpd <= 59:
        return Bucket.DPD_30_59
    if dpd <= 89:
        return Bucket.DPD_60_89
    return Bucket.DPD_90_PLUS
