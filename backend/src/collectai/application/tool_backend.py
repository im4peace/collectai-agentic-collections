"""Concrete `ToolBackendPort` implementation (E5-S4).

The seam `ai_orchestration.ports.ToolBackendPort` documents: `ToolBackend`
is the one place that turns a schema-validated tool call into a real
`rules_engine` calculation and/or a real persistence read, then maps the
result back into the `ai_orchestration.schemas` shape the registry's six
tools promise. `ai_orchestration/tools/registry.py` never calls this class
directly -- only through the Protocol it implements.

READ tools (`get_account_context`, `get_eligible_options`) are strictly
read-only. PROPOSE tools (`propose_ptp`, `flag_hardship`, `flag_dispute`,
`escalate_to_human`) run a deterministic check (PTP validation, escalation
routing) or a schema-validated echo (hardship/dispute flags), and are made
idempotent via `domain_services.idempotency.IdempotencyService` keyed on the
caller-supplied `idempotency_key` (AC3) -- no `Proposal`/`HardshipCase`/
`Dispute`/`EscalationCase` row is written by this story; see E6-S2 (PTP/
payment/arrangement proposal persistence) and E7-S1/E8-S2/E8-S3 (case
creation from a validated flag) for the later stories that do.

NOTE: over the code-gen skill's 200-line block-threshold note, driven by six
tool methods plus their per-tool result mapping; suppression-input assembly
is already split out to `_tool_backend_suppression.py`. If this grows
further, split the PROPOSE-tool methods into a sibling module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.ai_orchestration.schemas.tool_args import (
    EscalateToHumanArgs,
    FlagDisputeArgs,
    FlagHardshipArgs,
    GetAccountContextArgs,
    GetEligibleOptionsArgs,
    ProposePtpArgs,
)
from collectai.ai_orchestration.schemas.tool_results import (
    AccountContextResult,
    AmountRangeResult,
    ArrangementOptionSummary,
    DateRangeResult,
    EligibleOptionsResult,
    EscalateToHumanResult,
    FlagDisputeResult,
    FlagHardshipResult,
    PayableOptionResult,
    ProposePtpResult,
    PtpAlternativesResult,
    PtpDateWindowResult,
)
from collectai.ai_orchestration.tools.registry import ToolName
from collectai.application._tool_backend_suppression import build_suppression_input
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services._arrangement_helpers import has_active_arrangement
from collectai.domain_services._ptp_helpers import has_active_pending_ptp
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.rules_engine.arrangement import get_eligible_options as get_eligible_arrangements
from collectai.rules_engine.payable import get_payable_options
from collectai.rules_engine.ptp_rules import Alternatives, PtpValidationInput, validate_ptp
from collectai.rules_engine.routing import route_escalation
from collectai.rules_engine.suppression import evaluate_suppression
from collectai.types.clock import Clock
from collectai.types.enums import AccountType, Bucket, CollectionStatus, EligibilityClass


class AccountNotFoundForCustomerError(Exception):
    """Raised when `account_id` does not resolve to an account owned by
    `customer_id` (data-models.md AC6 ownership scoping). A future chat-flow
    story is responsible for turning this into a customer-safe response;
    this story only needs it to never be silently swallowed."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"No account {account_id!r} found for the bound customer.")


class ToolBackend:
    """Implements `ai_orchestration.ports.ToolBackendPort`."""

    def __init__(
        self,
        session: AsyncSession,
        policy_provider: PolicyProvider,
        clock: Clock,
        idempotency_service: IdempotencyService,
    ) -> None:
        self._session = session
        self._policy_provider = policy_provider
        self._clock = clock
        self._idempotency = idempotency_service

    async def get_account_context(
        self, customer_id: str, args: GetAccountContextArgs
    ) -> AccountContextResult:
        account = await AccountRepository().get_by_id_for_customer(
            self._session, args.account_id, customer_id
        )
        delinquency = await DelinquencyRecordRepository().get_by_account(
            self._session, args.account_id, customer_id
        )
        if account is None or delinquency is None:
            raise AccountNotFoundForCustomerError(args.account_id)
        return AccountContextResult(
            account_id=account.account_id,
            customer_id=account.customer_id,
            account_type=AccountType(account.account_type),
            product_name=account.product_name,
            opened_on=account.opened_on,
            outstanding_balance=delinquency.outstanding_balance,
            overdue_amount=delinquency.overdue_amount,
            dpd=delinquency.dpd,
            bucket=Bucket(delinquency.bucket),
            collection_status=CollectionStatus(delinquency.collection_status),
            as_of=delinquency.as_of,
            record_version=delinquency.record_version,
        )

    async def get_eligible_options(
        self, customer_id: str, args: GetEligibleOptionsArgs
    ) -> EligibleOptionsResult:
        """Payable amounts, the PTP date window, and (E8-S1 AC9)
        `arrangement_options` from `rules_engine.arrangement
        .get_eligible_options` -- real data now, without changing this
        method's return type (`EligibleOptionsResult`/`ArrangementOptionSummary`
        were already shaped for it in Slice 1). Empty when the account is not
        arrangement-eligible or the arrangement rules engine itself fails
        closed -- never a fabricated option."""
        delinquency = await DelinquencyRecordRepository().get_by_account(
            self._session, args.account_id, customer_id
        )
        if delinquency is None:
            raise AccountNotFoundForCustomerError(args.account_id)

        policy = self._policy_provider.get_active()
        suppression_input = await build_suppression_input(
            self._session, args.account_id, customer_id
        )
        treatment = evaluate_suppression(suppression_input, policy)
        payable = get_payable_options(
            delinquency.overdue_amount,
            delinquency.outstanding_balance,
            treatment.automated_treatment_suppressed,
            policy,
        )
        today = self._clock.now().date()
        window = PtpDateWindowResult(
            earliest=today,
            latest=today + timedelta(days=policy.parameters.ptp.window_days),
        )
        arrangement_options = await self._arrangement_options(args.account_id, delinquency)
        return EligibleOptionsResult(
            account_id=args.account_id,
            payable_options=[
                PayableOptionResult(option_type=option.option_type, amount=option.amount)
                for option in payable
            ],
            ptp_date_window=window,
            arrangement_options=arrangement_options,
        )

    async def _arrangement_options(
        self, account_id: str, delinquency: DelinquencyRecordOrm
    ) -> list[ArrangementOptionSummary]:
        has_ptp = await has_active_pending_ptp(self._session, account_id)
        has_arrangement = await has_active_arrangement(self._session, account_id)
        result = get_eligible_arrangements(
            self._policy_provider,
            self._clock,
            delinquency.overdue_amount,
            delinquency.dpd,
            has_ptp,
            has_arrangement,
        )
        if not result.ok or result.value is None:
            return []
        if result.value.classification is not EligibilityClass.ELIGIBLE:
            return []
        return [
            ArrangementOptionSummary(
                option_id=option.option_id,
                installment_count=option.installment_count,
                installment_amount=option.installment_amount,
                total_amount=option.total_amount,
                first_installment_date=option.first_installment_date,
            )
            for option in result.value.options
        ]

    async def propose_ptp(
        self, customer_id: str, idempotency_key: str, args: ProposePtpArgs
    ) -> ProposePtpResult:
        async def compute() -> dict[str, object]:
            delinquency = await DelinquencyRecordRepository().get_by_account(
                self._session, args.account_id, customer_id
            )
            if delinquency is None:
                raise AccountNotFoundForCustomerError(args.account_id)
            outcome = validate_ptp(
                PtpValidationInput(
                    promised_amount=args.promised_amount,
                    promised_date=args.promised_date,
                    overdue_amount=delinquency.overdue_amount,
                ),
                self._policy_provider,
                self._clock,
            )
            result = ProposePtpResult(
                account_id=args.account_id,
                promised_amount=args.promised_amount,
                promised_date=args.promised_date,
                valid=outcome.valid,
                reason_codes=list(outcome.reason_codes),
                alternatives=_to_alternatives_result(outcome.alternatives),
            )
            return result.model_dump(mode="json")

        body = await self._get_or_create(
            ToolName.PROPOSE_PTP, idempotency_key, args, "ptp_proposal", compute
        )
        return ProposePtpResult.model_validate(body)

    async def flag_hardship(
        self, customer_id: str, idempotency_key: str, args: FlagHardshipArgs
    ) -> FlagHardshipResult:
        async def compute() -> dict[str, object]:
            result = FlagHardshipResult(
                account_id=args.account_id, indicator_type=args.indicator_type, note=args.note
            )
            return result.model_dump(mode="json")

        body = await self._get_or_create(
            ToolName.FLAG_HARDSHIP, idempotency_key, args, "hardship_flag", compute
        )
        return FlagHardshipResult.model_validate(body)

    async def flag_dispute(
        self, customer_id: str, idempotency_key: str, args: FlagDisputeArgs
    ) -> FlagDisputeResult:
        async def compute() -> dict[str, object]:
            result = FlagDisputeResult(
                account_id=args.account_id,
                category=args.category,
                customer_reason=args.customer_reason,
                item_id=args.item_id,
            )
            return result.model_dump(mode="json")

        body = await self._get_or_create(
            ToolName.FLAG_DISPUTE, idempotency_key, args, "dispute_flag", compute
        )
        return FlagDisputeResult.model_validate(body)

    async def escalate_to_human(
        self, customer_id: str, idempotency_key: str, args: EscalateToHumanArgs
    ) -> EscalateToHumanResult:
        async def compute() -> dict[str, object]:
            routing = route_escalation(args.reason, self._policy_provider)
            result = EscalateToHumanResult(
                reason=routing.reason,
                queue=routing.queue,
                reviewer_role=routing.reviewer_role,
                priority=routing.priority,
                policy_version=routing.policy_version,
                flags=list(routing.flags),
                rationale=args.rationale,
            )
            return result.model_dump(mode="json")

        body = await self._get_or_create(
            ToolName.ESCALATE_TO_HUMAN, idempotency_key, args, "escalation_routing", compute
        )
        return EscalateToHumanResult.model_validate(body)

    async def _get_or_create(
        self,
        tool_name: ToolName,
        idempotency_key: str,
        args: BaseModel,
        resource_type: str,
        compute: Callable[[], Awaitable[dict[str, object]]],
    ) -> dict[str, object]:
        body, _ = await self._idempotency.get_or_create(
            self._session,
            scope=f"tool:{tool_name.value}",
            key=idempotency_key,
            request_hash=_request_hash(args),
            resource_type=resource_type,
            resource_id=None,
            compute_response=compute,
        )
        return body


def _request_hash(args: BaseModel) -> str:
    """sha256 of the canonical request body alone (no turn/tool prefix) --
    distinct from `idempotency_key`, which additionally scopes by turn and
    tool name. Kept for data-models.md's `idempotency_record.request_hash`
    column; this story never compares it (no 409 IDEMPOTENCY_KEY_REUSED path
    here -- see `domain_services/idempotency.py`'s docstring)."""
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_alternatives_result(alternatives: Alternatives | None) -> PtpAlternativesResult | None:
    if alternatives is None:
        return None
    amount_range = alternatives.valid_amount_range
    date_range = alternatives.valid_date_range
    return PtpAlternativesResult(
        valid_amount_range=(
            AmountRangeResult(min=amount_range.min, max=amount_range.max)
            if amount_range is not None
            else None
        ),
        valid_date_range=(
            DateRangeResult(earliest=date_range.earliest, latest=date_range.latest)
            if date_range is not None
            else None
        ),
    )

