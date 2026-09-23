"""E5-S4 AC1, AC2, AC6-AC9: the closed six-tool set and the dispatch loop's
budget/validation/audit behavior, against a fake `ToolBackendPort` (an
external boundary this suite does not need to hit for real -- the real
`ToolBackend` implementation is exercised against a real database in
`tests/db/test_e5_s4_tool_backend.py`). The `AuditService` boundary here is
faked the same way `test_e5_s2_orchestrator.py` fakes it: a recording stand
-in for the session factory `AuditService.record` opens its own transaction
against, so this suite runs without Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import TracebackType

import pytest

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
    EligibleOptionsResult,
    EscalateToHumanResult,
    FlagDisputeResult,
    FlagHardshipResult,
    ProposePtpResult,
    PtpDateWindowResult,
)
from collectai.ai_orchestration.tools.registry import (
    TOOL_CAP_REACHED_EVENT_TYPE,
    ToolCapReached,
    ToolError,
    ToolName,
    ToolSuccess,
    TurnToolCallBudget,
    dispatch_tool_call,
)
from collectai.audit.service import AuditService
from collectai.types.clock import SimulatedClock
from collectai.types.enums import (
    AccountType,
    Bucket,
    CollectionStatus,
    EscalationPriority,
    ReviewerRole,
    ReviewQueue,
)

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_000101"
_CUSTOMER_ID = "cus_000101"


class _FakeToolBackend:
    """Records every call it receives; returns a fixed, realistic result per
    tool so dispatch-level behavior can be asserted without a database."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    async def get_account_context(
        self, customer_id: str, args: GetAccountContextArgs
    ) -> AccountContextResult:
        self.calls.append(("get_account_context", customer_id, args))
        return AccountContextResult(
            account_id=args.account_id,
            customer_id=_CUSTOMER_ID,
            account_type=AccountType.PERSONAL_LOAN,
            product_name="Everyday Personal Loan",
            opened_on=date(2025, 3, 14),
            outstanding_balance="8420.10",
            overdue_amount="770.40",
            dpd=34,
            bucket=Bucket.DPD_30_59,
            collection_status=CollectionStatus.IN_PROGRESS,
            as_of=_NOW,
            record_version=7,
        )

    async def get_eligible_options(
        self, customer_id: str, args: GetEligibleOptionsArgs
    ) -> EligibleOptionsResult:
        self.calls.append(("get_eligible_options", customer_id, args))
        return EligibleOptionsResult(
            account_id=args.account_id,
            payable_options=[],
            ptp_date_window=PtpDateWindowResult(
                earliest=date(2026, 10, 1), latest=date(2026, 10, 31)
            ),
        )

    async def propose_ptp(
        self, customer_id: str, idempotency_key: str, args: ProposePtpArgs
    ) -> ProposePtpResult:
        self.calls.append(("propose_ptp", idempotency_key, args))
        return ProposePtpResult(
            account_id=args.account_id,
            promised_amount=args.promised_amount,
            promised_date=args.promised_date,
            valid=True,
            reason_codes=[],
        )

    async def flag_hardship(
        self, customer_id: str, idempotency_key: str, args: FlagHardshipArgs
    ) -> FlagHardshipResult:
        self.calls.append(("flag_hardship", idempotency_key, args))
        return FlagHardshipResult(
            account_id=args.account_id, indicator_type=args.indicator_type, note=args.note
        )

    async def flag_dispute(
        self, customer_id: str, idempotency_key: str, args: FlagDisputeArgs
    ) -> FlagDisputeResult:
        self.calls.append(("flag_dispute", idempotency_key, args))
        return FlagDisputeResult(
            account_id=args.account_id,
            category=args.category,
            customer_reason=args.customer_reason,
            item_id=args.item_id,
        )

    async def escalate_to_human(
        self, customer_id: str, idempotency_key: str, args: EscalateToHumanArgs
    ) -> EscalateToHumanResult:
        self.calls.append(("escalate_to_human", idempotency_key, args))
        return EscalateToHumanResult(
            reason=args.reason,
            queue=ReviewQueue.COLLECTIONS_REVIEW,
            reviewer_role=ReviewerRole.COLLECTIONS_OFFICER,
            priority=EscalationPriority.NORMAL,
            policy_version="policy-v1",
            flags=[],
            rationale=args.rationale,
        )


class _RecordingSessionCtx:
    def __init__(self, outer: _RecordingSessionFactory) -> None:
        self._outer = outer

    async def __aenter__(self) -> _RecordingSessionCtx:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def add(self, obj: object) -> None:
        self._outer.recorded.append(obj)

    async def commit(self) -> None:
        return None


class _RecordingSessionFactory:
    """Fakes the `async_sessionmaker` boundary `AuditService.record` opens
    its own transaction against (mirrors `test_e5_s2_orchestrator.py`)."""

    def __init__(self) -> None:
        self.recorded: list[object] = []

    def __call__(self) -> _RecordingSessionCtx:
        return _RecordingSessionCtx(self)


def _audit_service(factory: _RecordingSessionFactory) -> AuditService:
    return AuditService(SimulatedClock(_NOW), factory)  # type: ignore[arg-type]


def _get_account_context_call(**overrides: object) -> dict[str, object]:
    return {
        "tool_name": "get_account_context",
        "raw_args": {"account_id": _ACCOUNT_ID},
        **overrides,
    }


@pytest.mark.asyncio
async def test_tool_name_enum_is_exactly_the_six_named_tools() -> None:
    """AC1: closed set, not an open/extensible registry."""
    assert {member.value for member in ToolName} == {
        "get_account_context",
        "get_eligible_options",
        "propose_ptp",
        "flag_hardship",
        "flag_dispute",
        "escalate_to_human",
    }


@pytest.mark.asyncio
async def test_unknown_tool_name_returns_tool_error_and_never_executes() -> None:
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())

    outcome = await dispatch_tool_call(
        tool_name="delete_account",
        raw_args={"account_id": _ACCOUNT_ID},
        backend=backend,
        budget=TurnToolCallBudget(cap=5),
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolError)
    assert outcome.tool_name is None
    assert backend.calls == []


@pytest.mark.asyncio
async def test_invalid_arguments_return_tool_error_and_never_execute() -> None:
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())

    outcome = await dispatch_tool_call(
        tool_name="get_account_context",
        raw_args={"account_id": "not-a-valid-id"},
        backend=backend,
        budget=TurnToolCallBudget(cap=5),
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolError)
    assert outcome.tool_name == "get_account_context"
    assert backend.calls == []


@pytest.mark.asyncio
async def test_escalate_to_human_with_extra_destination_field_returns_tool_error() -> None:
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())

    outcome = await dispatch_tool_call(
        tool_name="escalate_to_human",
        raw_args={
            "reason": "REQUEST_HUMAN",
            "rationale": "Customer asked for a human.",
            "queue": "COLLECTIONS_REVIEW",
        },
        backend=backend,
        budget=TurnToolCallBudget(cap=5),
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolError)
    assert backend.calls == []


@pytest.mark.asyncio
async def test_get_account_context_happy_path_dispatches_to_backend() -> None:
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())

    outcome = await dispatch_tool_call(
        **_get_account_context_call(),
        backend=backend,
        budget=TurnToolCallBudget(cap=5),
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolSuccess)
    assert outcome.tool_name is ToolName.GET_ACCOUNT_CONTEXT
    assert isinstance(outcome.result, AccountContextResult)
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_propose_ptp_happy_path_computes_and_forwards_idempotency_key() -> None:
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())

    outcome = await dispatch_tool_call(
        tool_name="propose_ptp",
        raw_args={
            "account_id": _ACCOUNT_ID,
            "promised_amount": "250.00",
            "promised_date": "2026-10-15",
        },
        backend=backend,
        budget=TurnToolCallBudget(cap=5),
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolSuccess)
    assert isinstance(outcome.result, ProposePtpResult)
    [(_, idempotency_key, _args)] = backend.calls
    assert len(idempotency_key) == 64


@pytest.mark.asyncio
async def test_cap_boundary_at_five_lets_first_five_calls_execute() -> None:
    """AC7: the 4th and 5th calls execute."""
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())
    budget = TurnToolCallBudget(cap=5)

    for _ in range(5):
        outcome = await dispatch_tool_call(
            **_get_account_context_call(),
            backend=backend,
            budget=budget,
            turn_id="trn_001",
            customer_id=_CUSTOMER_ID,
            correlation_id="corr-001",
            audit_service=audit_service,
        )
        assert isinstance(outcome, ToolSuccess)

    assert len(backend.calls) == 5
    assert budget.calls_made == 5


@pytest.mark.asyncio
async def test_cap_boundary_sixth_call_is_blocked_and_writes_one_audit_event() -> None:
    """AC7, AC8: an attempted 6th call does not execute and cannot mutate
    state; exactly one TOOL_CAP_REACHED audit event is written for it."""
    backend = _FakeToolBackend()
    factory = _RecordingSessionFactory()
    audit_service = _audit_service(factory)
    budget = TurnToolCallBudget(cap=5)

    for _ in range(5):
        await dispatch_tool_call(
            **_get_account_context_call(),
            backend=backend,
            budget=budget,
            turn_id="trn_001",
            customer_id=_CUSTOMER_ID,
            correlation_id="corr-001",
            audit_service=audit_service,
        )
    assert len(backend.calls) == 5

    sixth_outcome = await dispatch_tool_call(
        **_get_account_context_call(),
        backend=backend,
        budget=budget,
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(sixth_outcome, ToolCapReached)
    assert sixth_outcome.tool_name == "get_account_context"
    assert len(backend.calls) == 5, "the 6th call must never reach the backend"

    cap_reached_events = [
        obj
        for obj in factory.recorded
        if getattr(obj, "event_type", None) == TOOL_CAP_REACHED_EVENT_TYPE
    ]
    assert len(cap_reached_events) == 1


@pytest.mark.asyncio
async def test_cap_reached_does_not_validate_or_execute_invalid_args() -> None:
    """AC8: even a request whose args would have failed validation never
    executes once the cap is already exhausted -- the cap check comes
    first."""
    backend = _FakeToolBackend()
    audit_service = _audit_service(_RecordingSessionFactory())
    budget = TurnToolCallBudget(cap=1)
    await dispatch_tool_call(
        **_get_account_context_call(),
        backend=backend,
        budget=budget,
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    outcome = await dispatch_tool_call(
        tool_name="not_a_real_tool",
        raw_args={"anything": "goes"},
        backend=backend,
        budget=budget,
        turn_id="trn_001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-001",
        audit_service=audit_service,
    )

    assert isinstance(outcome, ToolCapReached)
