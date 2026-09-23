"""Integration tests for `ToolBackend` (E5-S4) against a real, migrated
Postgres database -- proves the ORM/repository wiring, the real
`rules_engine` calls, and the real `IdempotencyService`/`AuditService`
writes that `tests/ai_guardrails/test_e5_s4_tool_registry.py`'s fakes stand
in for. AC3 (idempotent replay) and AC7/AC8 (cap boundary) specifically need
a real database: they assert actual `idempotency_record` and `audit_event`
row counts, not just in-memory call counts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from collectai.ai_orchestration.tools.registry import (
    TOOL_CAP_REACHED_EVENT_TYPE,
    ToolCapReached,
    ToolSuccess,
    TurnToolCallBudget,
    dispatch_tool_call,
)
from collectai.application.tool_backend import ToolBackend
from collectai.audit.service import AuditService
from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.audit_event import AuditEventOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.persistence.orm.escalation_case import EscalationCaseOrm
from collectai.persistence.orm.idempotency_record import IdempotencyRecordOrm
from collectai.types.clock import SimulatedClock
from collectai.types.money import Money

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_CUSTOMER_ID = "cus_000401"
_ACCOUNT_ID = "acc_000501"


async def _seed_account(
    session: AsyncSession, *, customer_id: str = _CUSTOMER_ID, account_id: str = _ACCOUNT_ID
) -> None:
    session.add(
        CustomerOrm(
            customer_id=customer_id,
            display_name="Taylor Whitfield",
            email="taylor.whitfield@example.com",
            phone="+1-555-0199",
            vulnerability_flag=False,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.flush()
    session.add(
        AccountOrm(
            account_id=account_id,
            customer_id=customer_id,
            account_type="PERSONAL_LOAN",
            product_name="Everyday Personal Loan",
            currency="USD",
            opened_on=date(2025, 3, 14),
            product_attributes={
                "original_principal": "12000.00",
                "term_months": "36",
                "monthly_installment": "385.20",
            },
            created_at=_NOW,
        )
    )
    session.add(
        DelinquencyRecordOrm(
            account_id=account_id,
            customer_id=customer_id,
            outstanding_balance=Money("8420.10"),
            overdue_amount=Money("770.40"),
            dpd=34,
            bucket="DPD_30_59",
            collection_status="IN_PROGRESS",
            as_of=_NOW,
            record_version=7,
            updated_at=_NOW,
        )
    )
    await session.commit()


async def _ensure_policy_rule_set_row(session: AsyncSession) -> None:
    """`escalation_case.routing_policy_version` FKs to `policy_rule_set`
    (migration `0006_system_tables`); mirrors
    `test_e3_s5_ownership_matrix.py`'s `_ensure_policy_rule_set_row`."""
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES ('policy-v1', '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) "
            "ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"created_at": _NOW},
    )


def _active_policy_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


@pytest.mark.asyncio
async def test_get_account_context_returns_real_account_and_delinquency_snapshot(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import GetAccountContextArgs

    result = await backend.get_account_context(
        _CUSTOMER_ID, GetAccountContextArgs(account_id=_ACCOUNT_ID)
    )

    assert result.account_id == _ACCOUNT_ID
    assert result.outstanding_balance == Money("8420.10")
    assert result.dpd == 34


@pytest.mark.asyncio
async def test_get_eligible_options_returns_payable_amounts_and_empty_arrangement_options(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import GetEligibleOptionsArgs

    result = await backend.get_eligible_options(
        _CUSTOMER_ID, GetEligibleOptionsArgs(account_id=_ACCOUNT_ID)
    )

    assert len(result.payable_options) == 2  # OVERDUE_AMOUNT and FULL_BALANCE per policy-v1
    assert result.ptp_date_window.earliest == date(2026, 10, 1)
    assert result.ptp_date_window.latest == date(2026, 10, 31)  # policy-v1 ptp.window_days=30
    assert result.arrangement_options == []  # AC5: always empty in Slice 1


@pytest.mark.asyncio
async def test_get_eligible_options_returns_no_payable_options_when_suppressed(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    await _ensure_policy_rule_set_row(session)
    session.add(
        EscalationCaseOrm(
            case_id="esc_000601",
            customer_id=_CUSTOMER_ID,
            account_id=_ACCOUNT_ID,
            reason="FINANCIAL_HARDSHIP",
            queue="HARDSHIP_REVIEW",
            reviewer_role="COLLECTIONS_OFFICER",
            priority="ELEVATED",
            status="OPEN",
            source="AI",
            summary="Customer reports job loss; hardship review requested.",
            routing_policy_version="policy-v1",
            routing_flags=[],
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    await session.commit()
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import GetEligibleOptionsArgs

    result = await backend.get_eligible_options(
        _CUSTOMER_ID, GetEligibleOptionsArgs(account_id=_ACCOUNT_ID)
    )

    assert result.payable_options == []


@pytest.mark.asyncio
async def test_propose_ptp_valid_amount_and_date_returns_valid_true(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import ProposePtpArgs

    result = await backend.propose_ptp(
        _CUSTOMER_ID,
        "idem-key-valid-001",
        ProposePtpArgs(
            account_id=_ACCOUNT_ID, promised_amount="250.00", promised_date=date(2026, 10, 15)
        ),
    )

    assert result.valid is True
    assert result.reason_codes == []
    assert result.alternatives is None


@pytest.mark.asyncio
async def test_propose_ptp_amount_over_balance_returns_alternatives(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import ProposePtpArgs

    result = await backend.propose_ptp(
        _CUSTOMER_ID,
        "idem-key-invalid-001",
        ProposePtpArgs(
            account_id=_ACCOUNT_ID, promised_amount="99999.00", promised_date=date(2026, 10, 15)
        ),
    )

    assert result.valid is False
    assert result.alternatives is not None
    assert result.alternatives.valid_amount_range is not None
    assert result.alternatives.valid_amount_range.max == Money("770.40")


@pytest.mark.asyncio
async def test_flag_hardship_returns_validated_echo(session: AsyncSession, clean_db: None) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import FlagHardshipArgs

    result = await backend.flag_hardship(
        _CUSTOMER_ID,
        "idem-key-hardship-001",
        FlagHardshipArgs(
            account_id=_ACCOUNT_ID, indicator_type="JOB_LOSS", note="Customer reports job loss."
        ),
    )

    assert result.account_id == _ACCOUNT_ID
    assert result.note == "Customer reports job loss."


@pytest.mark.asyncio
async def test_flag_dispute_returns_validated_echo(session: AsyncSession, clean_db: None) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import FlagDisputeArgs

    result = await backend.flag_dispute(
        _CUSTOMER_ID,
        "idem-key-dispute-001",
        FlagDisputeArgs(
            account_id=_ACCOUNT_ID,
            category="AMOUNT_INCORRECT",
            customer_reason="The installment amount looks wrong.",
        ),
    )

    assert result.category.value == "AMOUNT_INCORRECT"


@pytest.mark.asyncio
async def test_escalate_to_human_uses_the_real_routing_table(
    session: AsyncSession, clean_db: None
) -> None:
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    backend = ToolBackend(session, _active_policy_provider(clock), clock, IdempotencyService(clock))

    from collectai.ai_orchestration.schemas.tool_args import EscalateToHumanArgs

    result = await backend.escalate_to_human(
        _CUSTOMER_ID,
        "idem-key-escalate-001",
        EscalateToHumanArgs(reason="FINANCIAL_HARDSHIP", rationale="Customer reports job loss."),
    )

    # policy-v1's routing.table default (specs/policy-ruleset-contract.md section 3.9).
    assert result.queue.value == "HARDSHIP_REVIEW"
    assert result.reviewer_role.value == "COLLECTIONS_OFFICER"
    assert result.policy_version == "policy-v1"


@pytest.mark.asyncio
async def test_idempotent_replay_returns_identical_result_and_creates_exactly_one_row(
    session: AsyncSession, clean_db: None
) -> None:
    """AC3: repeating a PROPOSE call with the same idempotency key returns
    the original result and creates no second row."""
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    policy_provider = _active_policy_provider(clock)
    idempotency_service = IdempotencyService(clock)
    backend = ToolBackend(session, policy_provider, clock, idempotency_service)
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    audit_service = AuditService(clock, session_factory)
    budget = TurnToolCallBudget(cap=5)

    raw_args = {
        "account_id": _ACCOUNT_ID,
        "promised_amount": "250.00",
        "promised_date": "2026-10-15",
    }
    first = await dispatch_tool_call(
        tool_name="propose_ptp",
        raw_args=raw_args,
        backend=backend,
        budget=budget,
        turn_id="trn_REPLAY001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-replay-001",
        audit_service=audit_service,
    )
    second = await dispatch_tool_call(
        tool_name="propose_ptp",
        raw_args=raw_args,
        backend=backend,
        budget=budget,
        turn_id="trn_REPLAY001",
        customer_id=_CUSTOMER_ID,
        correlation_id="corr-replay-001",
        audit_service=audit_service,
    )

    assert isinstance(first, ToolSuccess)
    assert isinstance(second, ToolSuccess)
    assert first.result == second.result

    count = await session.scalar(
        select(func.count())
        .select_from(IdempotencyRecordOrm)
        .where(IdempotencyRecordOrm.scope == "tool:propose_ptp")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_cap_boundary_sixth_call_creates_no_idempotency_row_and_writes_one_audit_event(
    session: AsyncSession, clean_db: None
) -> None:
    """AC7, AC8: cap=5 lets the first 5 (distinct) PROPOSE calls execute and
    each write its own idempotency_record row; the 6th neither executes nor
    writes a row, and exactly one TOOL_CAP_REACHED audit event is written."""
    await _seed_account(session)
    clock = SimulatedClock(_NOW)
    policy_provider = _active_policy_provider(clock)
    idempotency_service = IdempotencyService(clock)
    backend = ToolBackend(session, policy_provider, clock, idempotency_service)
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    audit_service = AuditService(clock, session_factory)
    budget = TurnToolCallBudget(cap=5)

    outcomes = []
    for day in range(5, 11):  # 6 distinct promised_dates -> 6 distinct idempotency keys
        outcome = await dispatch_tool_call(
            tool_name="propose_ptp",
            raw_args={
                "account_id": _ACCOUNT_ID,
                "promised_amount": "250.00",
                "promised_date": f"2026-10-{day:02d}",
            },
            backend=backend,
            budget=budget,
            turn_id="trn_CAP001",
            customer_id=_CUSTOMER_ID,
            correlation_id="corr-cap-001",
            audit_service=audit_service,
        )
        outcomes.append(outcome)

    assert all(isinstance(outcome, ToolSuccess) for outcome in outcomes[:5])
    assert isinstance(outcomes[5], ToolCapReached)

    idempotency_count = await session.scalar(
        select(func.count())
        .select_from(IdempotencyRecordOrm)
        .where(IdempotencyRecordOrm.scope == "tool:propose_ptp")
    )
    assert idempotency_count == 5

    audit_count = await session.scalar(
        select(func.count())
        .select_from(AuditEventOrm)
        .where(AuditEventOrm.event_type == TOOL_CAP_REACHED_EVENT_TYPE)
    )
    assert audit_count == 1
