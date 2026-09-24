"""Payment arrangement creation from a confirmed chat proposal (E8-S1
AC3, AC5, AC8).

Mirrors `ptp_service.record_chat_ptp`'s own "revalidate everything again,
independent of what was true at offer time, then write" shape --
`application._confirmation_apply._confirm_arrangement` is this module's
only caller, itself called only from the customer's explicit confirm action
(D-041; CLAUDE.md's core engineering principle: the LLM never creates the
`PaymentArrangement` itself). `application.confirmation_flow`'s own
`_revalidate_freshness` already re-checked the delinquency snapshot's
`record_version`/staleness before this module ever runs; this module's own
job is arrangement-specific: re-run `rules_engine.arrangement
.get_eligible_options` fresh and confirm the offered `option_id` is still
among the *current* options, never trusting `proposal.terms` alone (state --
DPD, overdue amount, a new conflicting PTP/arrangement -- can have changed
since the offer, even within the proposal's own TTL).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._arrangement_exceptions import (
    ArrangementConflictError,
    ArrangementNotEligibleError,
)
from collectai.domain_services._arrangement_helpers import has_active_arrangement
from collectai.domain_services._ptp_helpers import has_active_pending_ptp, has_open_dispute
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.payment_arrangement import PaymentArrangementOrm
from collectai.rules_engine.arrangement import ArrangementOption, get_eligible_options

# `build_option` is not re-exported from `rules_engine.arrangement`'s public
# surface (only the *standard*, policy-menu path -- `get_eligible_options`
# -- is): E7-S4's exceptional-approval path needs the same exact-sum
# schedule math for a customer-requested, off-menu installment count, so it
# reaches into this private submodule directly rather than duplicating the
# math. Still layer 5a (domain_services) importing layer 4a (rules_engine)
# -- no architecture-boundary violation, just past the package's own
# "public API" convention.
from collectai.rules_engine.arrangement._schedule import build_option
from collectai.types.clock import Clock
from collectai.types.enums import (
    ActorKind,
    ArrangementCreatedVia,
    ArrangementStatus,
    AuditStage,
    EligibilityClass,
    Persona,
)
from collectai.types.ids import EntityPrefix, generate_id
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

ARRANGEMENT_CREATED_EVENT_TYPE = "ARRANGEMENT_CREATED"


async def create_arrangement_from_confirmed_proposal(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    option_id: str,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PaymentArrangementOrm:
    """E8-S1 AC3: revalidate authorization (the caller, `_confirm_arrangement`,
    only runs after `confirmation_flow`'s object-level/freshness checks),
    policy, freshness (a fresh `get_eligible_options()` call, not the
    proposal's stored terms) and option validity, then create with status
    ACTIVE. Raises `ArrangementNotEligibleError` for every way that
    revalidation can fail; the caller maps it to `ProposalInvalidError`.
    E8-S3 AC3: an open dispute on the account -- checked first, since it is
    a harder block than mere ineligibility -- raises `ArrangementConflictError`
    (`DISPUTED_ITEM`) instead, mirroring `_ptp_validation.assert_no_conflict`'s
    own dispute check for PTP creation."""
    if await has_open_dispute(session, account_id=record.account_id, item_id=None):
        raise ArrangementConflictError(
            reason_code=ReasonCode.DISPUTED_ITEM, message="This item is under an open dispute."
        )
    has_ptp = await has_active_pending_ptp(session, record.account_id)
    has_arrangement = await has_active_arrangement(session, record.account_id)
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable as exc:
        raise ArrangementNotEligibleError(
            "Arrangement options are not available right now."
        ) from exc

    result = get_eligible_options(
        policy_provider, clock, record.overdue_amount, record.dpd, has_ptp, has_arrangement
    )
    if not result.ok or result.value is None:
        raise ArrangementNotEligibleError("Arrangement options are not available right now.")
    if result.value.classification is not EligibilityClass.ELIGIBLE:
        raise ArrangementNotEligibleError(
            "This account is no longer eligible for a payment arrangement."
        )
    option = _find_option(result.value.options, option_id)
    if option is None:
        raise ArrangementNotEligibleError(
            "This arrangement option is no longer available; please ask for options again."
        )

    return await _insert_arrangement(
        session,
        record=record,
        option=option,
        created_via=ArrangementCreatedVia.CUSTOMER_CONFIRMATION,
        exception_case_id=None,
        policy_version=policy.policy_version,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        actor_persona=Persona.CUSTOMER,
    )


async def create_exceptional_arrangement_from_review(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    installment_count: int,
    exception_case_id: str,
    reviewer_persona: Persona,
    policy_provider: PolicyProvider,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
) -> PaymentArrangementOrm:
    """E7-S4 AC5: revalidate authorization (the caller, `review_service
    .decide`, only runs this after its own object-level/policy-authority
    checks), an open dispute and an existing active PTP/arrangement (the
    same hard safety block the standard path enforces -- exception
    authority widens *which terms* an officer may approve, never whether a
    second concurrent arrangement is allowed), then create with status
    ACTIVE using the exact-sum schedule math for the customer's own
    requested (off-menu) installment count -- never a value re-derived from
    `EscalationCase.requested_terms`'s stored, possibly stale date; the
    first installment date is always computed fresh, "tomorrow" relative to
    *now* (approval time), exactly as the standard offer path does."""
    if await has_open_dispute(session, account_id=record.account_id, item_id=None):
        raise ArrangementConflictError(
            reason_code=ReasonCode.DISPUTED_ITEM, message="This item is under an open dispute."
        )
    if await has_active_pending_ptp(
        session, record.account_id
    ) or await has_active_arrangement(session, record.account_id):
        raise ArrangementConflictError(
            reason_code=ReasonCode.CONFLICTING_ACTIVE_ITEM,
            message="This account already has an active promise to pay or payment plan.",
        )
    try:
        policy = policy_provider.get_active()
    except PolicyUnavailable as exc:
        raise ArrangementNotEligibleError(
            "Arrangement options are not available right now."
        ) from exc

    first_date: date = clock.now().date() + timedelta(days=1)
    option = build_option(installment_count, record.overdue_amount, first_date)
    return await _insert_arrangement(
        session,
        record=record,
        option=option,
        created_via=ArrangementCreatedVia.EXCEPTION_APPROVAL,
        exception_case_id=exception_case_id,
        policy_version=policy.policy_version,
        clock=clock,
        audit_service=audit_service,
        correlation_id=correlation_id,
        actor_persona=reviewer_persona,
    )


async def _insert_arrangement(
    session: AsyncSession,
    *,
    record: DelinquencyRecordOrm,
    option: ArrangementOption,
    created_via: ArrangementCreatedVia,
    exception_case_id: str | None,
    policy_version: str,
    clock: Clock,
    audit_service: AuditService,
    correlation_id: str,
    actor_persona: Persona,
) -> PaymentArrangementOrm:
    now = clock.now()
    row = PaymentArrangementOrm(
        arrangement_id=generate_id(EntityPrefix.ARRANGEMENT),
        account_id=record.account_id,
        customer_id=record.customer_id,
        status=ArrangementStatus.ACTIVE.value,
        created_via=created_via.value,
        exception_case_id=exception_case_id,
        option_id=option.option_id,
        installment_count=option.installment_count,
        installment_amount=option.installment_amount,
        final_installment_amount=option.final_installment_amount,
        total_amount=option.total_amount,
        first_installment_date=option.first_installment_date,
        frequency=option.frequency,
        schedule=[
            {
                "sequence": entry.sequence,
                "due_date": entry.due_date.isoformat(),
                "amount": entry.amount.to_api_string(),
            }
            for entry in option.schedule
        ],
        policy_version=policy_version,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(row)
    await session.flush()
    await audit_service.record_in(
        session,
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.FINAL_STATE,
            event_type=ARRANGEMENT_CREATED_EVENT_TYPE,
            actor_kind=ActorKind.STAFF if exception_case_id else ActorKind.SYSTEM,
            actor_persona=actor_persona,
            customer_id=row.customer_id,
            account_id=row.account_id,
            policy_version=row.policy_version,
            final_action=ARRANGEMENT_CREATED_EVENT_TYPE,
            resource_type="payment_arrangement",
            resource_id=row.arrangement_id,
        ),
    )
    return row


def _find_option(options: list[ArrangementOption], option_id: str) -> ArrangementOption | None:
    return next((option for option in options if option.option_id == option_id), None)


def arrangement_wire_dict(row: PaymentArrangementOrm) -> dict[str, object]:
    """The `PaymentArrangement` API shape -- matches `api.schemas.me
    .PaymentArrangement`/`ArrangementOption`/`ScheduleEntry` field-for-field
    (the same nested shape `api/routers/me_views.arrangement_view` already
    builds for `GET /api/me/arrangements/{id}`) so
    `api.schemas.chat_proposals.ConfirmResult.model_validate` can parse this
    plain dict without a schema mismatch. A plain, JSON-safe dict rather
    than that Pydantic model itself: `domain_services` (layer 5a) may never
    import `api.schemas` (layer 7) -- see `proposal_service.py`'s own
    module docstring for this codebase's established convention."""
    return {
        "arrangement_id": row.arrangement_id,
        "account_id": row.account_id,
        "status": row.status,
        "option": {
            "option_id": row.option_id,
            "installment_count": row.installment_count,
            "installment_amount": row.installment_amount.to_api_string(),
            "final_installment_amount": row.final_installment_amount.to_api_string(),
            "total_amount": row.total_amount.to_api_string(),
            "first_installment_date": row.first_installment_date.isoformat(),
            "frequency": row.frequency,
            "schedule": [
                {
                    "sequence": entry["sequence"],  # type: ignore[index]
                    "due_date": entry["due_date"],  # type: ignore[index]
                    "amount": entry["amount"],  # type: ignore[index]
                }
                for entry in row.schedule
            ],
        },
        "created_via": row.created_via,
        "exception_case_id": row.exception_case_id,
        "policy_version": row.policy_version,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
    }
