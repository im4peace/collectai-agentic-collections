"""Tests for `domain_services.ptp_lifecycle.validate_ptp_transition` (E6-S4
AC6). Pure and DB-free."""

from __future__ import annotations

import pytest

from collectai.domain_services.ptp_lifecycle import (
    InvalidPtpTransitionError,
    validate_ptp_transition,
)
from collectai.types.enums import PtpStatus


@pytest.mark.parametrize(
    "target", [PtpStatus.KEPT, PtpStatus.BROKEN, PtpStatus.CANCELLED]
)
def test_pending_may_transition_to_any_terminal_state(target: PtpStatus) -> None:
    validate_ptp_transition(PtpStatus.PENDING, target)


def test_same_status_is_not_a_transition() -> None:
    validate_ptp_transition(PtpStatus.PENDING, PtpStatus.PENDING)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (PtpStatus.KEPT, PtpStatus.PENDING),
        (PtpStatus.BROKEN, PtpStatus.PENDING),
        (PtpStatus.KEPT, PtpStatus.BROKEN),
        (PtpStatus.BROKEN, PtpStatus.KEPT),
        (PtpStatus.CANCELLED, PtpStatus.PENDING),
    ],
)
def test_every_other_transition_is_rejected(current: PtpStatus, target: PtpStatus) -> None:
    with pytest.raises(InvalidPtpTransitionError):
        validate_ptp_transition(current, target)
