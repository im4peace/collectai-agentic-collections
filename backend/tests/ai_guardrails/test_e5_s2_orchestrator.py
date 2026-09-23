"""E5-S2 AC1, AC2, AC3, AC5, AC6: the fail-closed AI write path.

The audit boundary is faked (a recording, optionally-failing stand-in for
the session factory `AuditService` opens its own transaction with), per the
code-gen skill's "only mock external boundaries: databases" -- `AuditService`
itself, its redaction and its field mapping are exercised for real; only
the actual database connection is replaced, so tests here run without
Postgres, matching the other `bt/ai_guardrails/` suites.

NOTE: past the code-gen skill's 200-line warning threshold. If this grows
further, split the AC5/AC6 cases into their own file rather than adding
more here."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType

import pytest
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.ports import DomainWriteOutcome
from collectai.audit.service import AuditService
from collectai.llm_provider.base import ProviderRequest, ProviderResult, ProviderTimeout
from collectai.llm_provider.mock import MockProvider
from collectai.types.clock import SimulatedClock
from collectai.types.enums import ProviderMode, SafeState

_NOW = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)


class _DemoProposal(BaseModel):
    action: str
    amount: str


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
        if self._outer.fail:
            raise SQLAlchemyError("simulated audit persistence failure")


class _RecordingSessionFactory:
    """Fakes the `async_sessionmaker` boundary `AuditService.record` opens
    its own transaction against."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.recorded: list[object] = []

    def __call__(self) -> _RecordingSessionCtx:
        return _RecordingSessionCtx(self)


class _StubDomainPort:
    def __init__(self, outcome: DomainWriteOutcome) -> None:
        self._outcome = outcome
        self.calls: list[_DemoProposal] = []

    async def apply(self, structured_output: _DemoProposal) -> DomainWriteOutcome:
        self.calls.append(structured_output)
        return self._outcome


def _context(*, correlation_id: str = "corr-e5s2-001") -> AiCallContext:
    return AiCallContext(
        correlation_id=correlation_id,
        capability="TEST_CAPABILITY",
        prompt_version="test_v1",
        provider_name="mock",
        provider_mode=ProviderMode.MOCK,
        policy_version="policy-v1",
    )


def _request() -> ProviderRequest:
    return ProviderRequest(messages=[{"role": "user", "content": "hi"}], max_tokens=100)


def _valid_result(*, latency_ms: float = 100.0) -> ProviderResult:
    return ProviderResult(
        content='{"action": "PROPOSE_PTP", "amount": "150.00"}',
        model_id="mock-model-1",
        latency_ms=latency_ms,
        input_tokens=50,
        output_tokens=20,
    )


def _invalid_result() -> ProviderResult:
    return ProviderResult(content="not json {{{", model_id="mock-model-1", latency_ms=50.0)


def _audit_service(factory: _RecordingSessionFactory) -> AuditService:
    return AuditService(SimulatedClock(_NOW), factory)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ac1_malformed_output_exhausted_retry_is_a_safe_response() -> None:
    provider = MockProvider([_invalid_result(), _invalid_result()])
    factory = _RecordingSessionFactory()

    result = await run_ai_interaction(
        provider, _request(), _DemoProposal, _context(), _audit_service(factory), retry_bound=1
    )

    assert result.safe_state is SafeState.AI_UNAVAILABLE
    assert result.structured_output is None
    assert result.domain_outcome is None
    assert result.governed is False
    assert len(factory.recorded) == 1
    recorded = factory.recorded[0]
    assert recorded.event_type == "AI_OUTPUT_INVALID"
    assert recorded.ai_output == {"raw": "not json {{{"}


@pytest.mark.asyncio
async def test_ac2_provider_timeout_exhausted_retry_is_a_safe_fallback_offering_handoff() -> None:
    timeout_error = ProviderTimeout(provider="mock", timeout_seconds=20)
    provider = MockProvider([timeout_error, timeout_error])
    factory = _RecordingSessionFactory()

    result = await run_ai_interaction(
        provider, _request(), _DemoProposal, _context(), _audit_service(factory), retry_bound=1
    )

    assert result.safe_state is SafeState.AI_UNAVAILABLE
    assert result.offer_handoff is True
    assert result.structured_output is None
    assert len(factory.recorded) == 1
    assert factory.recorded[0].event_type == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ac3_domain_rejection_prevails_and_writes_a_policy_conflict_event() -> None:
    provider = MockProvider([_valid_result()])
    factory = _RecordingSessionFactory()
    outcome = DomainWriteOutcome(
        applied=False,
        reason_code="OVER_BALANCE",
        rule_results={"priority_band": "HIGH"},
        final_action=None,
        resource_type="promise_to_pay",
        resource_id=None,
    )
    port = _StubDomainPort(outcome)

    result = await run_ai_interaction(
        provider,
        _request(),
        _DemoProposal,
        _context(),
        _audit_service(factory),
        domain_port=port,
    )

    assert len(port.calls) == 1
    assert result.domain_outcome is outcome
    assert result.domain_outcome is not None and result.domain_outcome.applied is False
    assert result.governed is True
    recorded = factory.recorded[0]
    assert recorded.event_type == "POLICY_CONFLICT"
    assert recorded.reason_code == "OVER_BALANCE"
    assert recorded.rule_results == {"priority_band": "HIGH"}


@pytest.mark.asyncio
async def test_ac5_audit_failure_on_a_material_recommendation_returns_safe_unavailable() -> None:
    """No `domain_port`: an advisory, non-state-changing AI response (e.g. a
    material recommendation) whose own audit write fails."""
    provider = MockProvider([_valid_result()])
    factory = _RecordingSessionFactory(fail=True)

    result = await run_ai_interaction(
        provider, _request(), _DemoProposal, _context(), _audit_service(factory)
    )

    assert result.safe_state is SafeState.AUDIT_UNAVAILABLE
    assert result.governed is False
    assert result.structured_output == _DemoProposal(action="PROPOSE_PTP", amount="150.00")


@pytest.mark.asyncio
async def test_ac5_audit_failure_on_a_domain_rejection_also_returns_safe_unavailable() -> None:
    provider = MockProvider([_valid_result()])
    factory = _RecordingSessionFactory(fail=True)
    outcome = DomainWriteOutcome(
        applied=False,
        reason_code="OVER_BALANCE",
        rule_results=None,
        final_action=None,
        resource_type=None,
        resource_id=None,
    )
    port = _StubDomainPort(outcome)

    result = await run_ai_interaction(
        provider,
        _request(),
        _DemoProposal,
        _context(),
        _audit_service(factory),
        domain_port=port,
    )

    assert result.safe_state is SafeState.AUDIT_UNAVAILABLE
    assert result.governed is False


@pytest.mark.asyncio
async def test_ac6_audit_event_records_full_ai_interaction_metadata() -> None:
    provider = MockProvider([_valid_result(latency_ms=123.4)])
    factory = _RecordingSessionFactory()
    context = _context(correlation_id="corr-e5s2-ac6")

    result = await run_ai_interaction(
        provider,
        _request(),
        _DemoProposal,
        context,
        _audit_service(factory),
        tool_call_duration_ms=42.0,
    )

    assert result.governed is True
    event = factory.recorded[0]
    assert event.correlation_id == "corr-e5s2-ac6"
    assert event.model_id == "mock-model-1"
    assert event.prompt_version == "test_v1"
    assert event.policy_version == "policy-v1"
    assert event.provider == "mock"
    assert event.provider_mode == "MOCK"
    assert event.latency["provider_latency_ms"] == 123.4
    assert event.latency["tool_call_duration_ms"] == 42.0
    assert "interaction_duration_ms" in event.latency
    assert event.token_usage == {"input_tokens": 50, "output_tokens": 20}
