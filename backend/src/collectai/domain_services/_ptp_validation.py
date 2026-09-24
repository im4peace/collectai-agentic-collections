"""Shared freshness/amount-date/conflict assertions for both PTP creation
paths (E6-S6's `ptp_service.record_officer_ptp` and E6-S2's
`_ptp_chat_confirmation.record_chat_ptp`), split into their own module so
neither creation-orchestration module has to duplicate them and neither
grows past the code-gen skill's 300-line block threshold.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.config.policy.models import PolicyRuleSet
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._ptp_exceptions import PtpBusinessRuleViolation, PtpConflictError
from collectai.domain_services._ptp_helpers import (
    PtpRecordRequest,
    alternatives_to_dict,
    business_violation_message,
    has_active_pending_ptp,
    has_open_dispute,
)
from collectai.rules_engine.freshness import check_freshness
from collectai.rules_engine.ptp_rules import PtpValidationInput, validate_ptp
from collectai.types.clock import Clock
from collectai.types.enums import Freshness
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode


def assert_fresh(
    request: PtpRecordRequest, domain_record: DelinquencyRecord, policy: PolicyRuleSet, clock: Clock
) -> None:
    freshness_result = check_freshness(
        snapshot_as_of=request.snapshot_as_of,
        snapshot_version=request.record_version,
        current_record=domain_record,
        policy=policy,
        clock=clock,
    )
    if freshness_result.status is not Freshness.FRESH:
        raise PtpConflictError(
            reason_code=freshness_result.reason_code or ReasonCode.AMBIGUOUS_VALIDATION,
            message=f"Snapshot freshness check failed: {freshness_result.status.value}.",
            context={"refreshed_context": {"record_version": domain_record.record_version}},
        )


def assert_amount_and_date_valid(
    request: PtpRecordRequest, overdue_amount: Money, policy_provider: PolicyProvider, clock: Clock
) -> None:
    outcome = validate_ptp(
        PtpValidationInput(
            promised_amount=request.promised_amount,
            promised_date=request.promised_date,
            overdue_amount=overdue_amount,
        ),
        policy_provider,
        clock,
    )
    if not outcome.valid:
        reason_code = outcome.reason_codes[0]
        raise PtpBusinessRuleViolation(
            reason_code=reason_code,
            message=business_violation_message(reason_code),
            alternatives=alternatives_to_dict(outcome.alternatives),
        )


async def assert_no_conflict(session: AsyncSession, request: PtpRecordRequest) -> None:
    if await has_active_pending_ptp(session, request.account_id):
        raise PtpConflictError(
            reason_code=ReasonCode.CONFLICTING_ACTIVE_ITEM,
            message="This account already has an active PENDING promise to pay.",
            context={"permitted_paths": ["cancel", "amend"]},
        )
    if await has_open_dispute(session, account_id=request.account_id, item_id=request.item_id):
        raise PtpConflictError(
            reason_code=ReasonCode.DISPUTED_ITEM,
            message="This item is under an open dispute.",
        )
