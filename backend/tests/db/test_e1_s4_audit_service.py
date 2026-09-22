"""Integration tests for `AuditService` against a real, migrated Postgres
database (E1-S4 AC1, AC3, AC5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from collectai.audit import queries
from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService, AuditUnavailable
from collectai.persistence.db import UnitOfWork
from collectai.types.clock import SimulatedClock
from collectai.types.enums import ActorKind, AuditStage, ProviderMode

pytestmark = pytest.mark.db

_NOW = datetime(2026, 10, 1, 9, 15, 30, tzinfo=UTC)


def _full_draft(*, correlation_id: str) -> AuditEventDraft:
    return AuditEventDraft(
        correlation_id=correlation_id,
        stage=AuditStage.AI_INTERPRETATION,
        event_type="NBA_GENERATED",
        actor_kind=ActorKind.AI,
        actor_persona=None,
        customer_id="cus_000101",
        account_id="acc_000123",
        capability="NEXT_BEST_ACTION",
        provider="anthropic",
        provider_mode=ProviderMode.LIVE,
        model_id="claude-sonnet-demo",
        prompt_version="nba_v1",
        policy_version="policy-v1",
        input_ref="ctx_ref_abc123",
        ai_output={"action": "SEND_REMINDER"},
        tool_calls=[{"tool": "get_account_context", "arguments": {}}],
        rule_results={"priority_band": "HIGH"},
        human_override=None,
        final_action="SEND_REMINDER",
        reason_code=None,
        resource_type="recommendation",
        resource_id="rec_000001",
        latency={"provider_latency_ms": 412.5},
        token_usage={"input_tokens": 512, "output_tokens": 128},
    )


@pytest.mark.asyncio
async def test_record_in_persists_every_ac1_field_stamped_from_the_injected_clock(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    clock = SimulatedClock(_NOW)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = AuditService(clock, session_factory)
    draft = _full_draft(correlation_id="corr-e1s4-roundtrip-001")

    async with UnitOfWork(session_factory) as uow_session:
        await service.record_in(uow_session, draft)

    stored = await queries.list_by_correlation_id(session, "corr-e1s4-roundtrip-001")
    assert len(stored) == 1
    event = stored[0]
    assert event.audit_event_id.startswith("aud_")
    assert isinstance(event.sequence, int)
    assert event.timestamp == _NOW
    assert event.stage is AuditStage.AI_INTERPRETATION
    assert event.actor_kind is ActorKind.AI
    assert event.customer_id == "cus_000101"
    assert event.account_id == "acc_000123"
    assert event.capability == "NEXT_BEST_ACTION"
    assert event.provider == "anthropic"
    assert event.provider_mode is ProviderMode.LIVE
    assert event.model_id == "claude-sonnet-demo"
    assert event.prompt_version == "nba_v1"
    assert event.policy_version == "policy-v1"
    assert event.tool_calls == [{"tool": "get_account_context", "arguments": {}}]
    assert event.rule_results == {"priority_band": "HIGH"}
    assert event.final_action == "SEND_REMINDER"
    assert event.resource_type == "recommendation"
    assert event.resource_id == "rec_000001"
    assert event.latency == {"provider_latency_ms": 412.5}
    assert event.token_usage == {"input_tokens": 512, "output_tokens": 128}


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_an_unknown_id(session: AsyncSession) -> None:
    assert await queries.get_by_id(session, "aud_DOESNOTEXIST00001") is None


@pytest.mark.asyncio
async def test_record_in_redacts_a_secret_in_input_ref_before_storing(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    clock = SimulatedClock(_NOW)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = AuditService(clock, session_factory)
    draft = _full_draft(correlation_id="corr-e1s4-redaction-001").model_copy(
        update={"input_ref": "raw prompt included key sk-ant-api03-abcdEFGH12345678"}
    )

    async with UnitOfWork(session_factory) as uow_session:
        await service.record_in(uow_session, draft)

    stored = await queries.list_by_correlation_id(session, "corr-e1s4-redaction-001")
    assert len(stored) == 1
    assert "[REDACTED]" in (stored[0].input_ref or "")
    assert "sk-ant-api03-abcdEFGH12345678" not in (stored[0].input_ref or "")


@pytest.mark.asyncio
async def test_record_in_failure_rolls_back_the_entire_transaction(
    engine: AsyncEngine, session: AsyncSession, clean_db: None
) -> None:
    """AC3: a second `record_in` call with a duplicate id violates the
    primary key inside the same `UnitOfWork` as an unrelated business write
    (a raw `idempotency_record` insert); the whole transaction, including
    that unrelated write and the first (otherwise valid) audit insert, must
    roll back -- nothing persists."""
    clock = SimulatedClock(_NOW)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fixed_id = "aud_FIXEDROLLBACKTEST01"
    service = AuditService(clock, session_factory, id_factory=lambda: fixed_id)
    draft = _full_draft(correlation_id="corr-e1s4-rollback-001")

    with pytest.raises(IntegrityError):
        async with UnitOfWork(session_factory) as uow_session:
            await uow_session.execute(
                text(
                    "INSERT INTO idempotency_record "
                    "(scope, idempotency_key, request_hash, response_status, "
                    "response_body, created_at) "
                    "VALUES ('audit-rollback-test', 'key-001', "
                    "'0000000000000000000000000000000000000000000000000000000000000000', "
                    "200, '{}'::jsonb, :created_at)"
                ),
                {"created_at": _NOW},
            )
            await service.record_in(uow_session, draft)  # first insert: succeeds within the tx
            await service.record_in(uow_session, draft)  # second insert: duplicate PK, raises

    assert await queries.get_by_id(session, fixed_id) is None
    remaining = await session.execute(
        text(
            "SELECT count(*) FROM idempotency_record "
            "WHERE scope = 'audit-rollback-test' AND idempotency_key = 'key-001'"
        )
    )
    assert remaining.scalar_one() == 0


@pytest.mark.asyncio
async def test_record_raises_audit_unavailable_on_persistence_failure(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """AC5: `record()` (the non-transactional path) raises `AuditUnavailable`
    when the insert fails, so the caller cannot report the activity as
    audited."""
    clock = SimulatedClock(_NOW)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fixed_id = "aud_FIXEDUNAVAILABLE001"
    service = AuditService(clock, session_factory, id_factory=lambda: fixed_id)
    draft = _full_draft(correlation_id="corr-e1s4-unavailable-001")

    await service.record(draft)  # first call: succeeds, occupies fixed_id

    with pytest.raises(AuditUnavailable) as exc_info:
        await service.record(draft)  # second call: duplicate PK -> AuditUnavailable

    assert exc_info.value.event_type == "NBA_GENERATED"
    assert exc_info.value.correlation_id == "corr-e1s4-unavailable-001"


@pytest.mark.asyncio
async def test_record_failure_log_contains_no_customer_data(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    clock = SimulatedClock(_NOW)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fixed_id = "aud_FIXEDLOGCHECK000001"
    service = AuditService(clock, session_factory, id_factory=lambda: fixed_id)
    draft = _full_draft(correlation_id="corr-e1s4-logcheck-001")
    await service.record(draft)

    with caplog.at_level("ERROR"):
        with pytest.raises(AuditUnavailable):
            await service.record(draft)

    for record in caplog.records:
        assert "cus_000101" not in record.getMessage()
        assert "cus_000101" not in str(getattr(record, "customer_id", ""))
        assert "acc_000123" not in str(record.__dict__)
        assert "ctx_ref_abc123" not in str(record.__dict__)
