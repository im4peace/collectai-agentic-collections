"""The MOCK/LIVE evaluation runner (E10-S1 AC2, AC3, AC4).

Each case runs the *real* intent-classification prompt/schema/orchestrator
(`ai_orchestration.prompts.intent_v1`, `ai_orchestration.orchestrator
.run_ai_interaction`) and the *real* deterministic precedence rule
(`ai_orchestration.safety_precedence.apply_safety_precedence`, reusing
`application._chat_reply_planning._sensitive_customer_message_reason` for
the escalation-reason precedence) -- the same building blocks a live chat
turn uses, just without the `ConversationOrm`/chat-turn persistence wrapper
a real turn also does (this framework only evaluates the AI+deterministic
decision, never writes a chat_message/chat_turn row).

`expected_escalation_reason` is scored only for the reasons a single
classified message alone determines (REQUEST_HUMAN and every `decision
.sensitive` case) -- UNRESOLVED_UNKNOWN (needs 3 consecutive turns) and
AMBIGUOUS_VALIDATION (a confirm-time freshness check, not a classification
outcome) are recorded on their dataset cases as documentation only (AC5's
"where applicable"), never compared against a predicted value here.

MOCK mode makes zero network calls: `MockProvider` (no scripted responses
given) always returns the same fixed valid response, so is deliberately
never the provider a real accuracy signal comes from in this repo's own
demo runs -- MOCK's value here is proving the harness itself (schema
validation, scoring, storage) works, not measuring a real model's accuracy.
LIVE mode calls the real Anthropic provider and requires both an explicit
opt-in and a real API key; it always refuses under CI (AC3)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from collectai.ai_orchestration.orchestrator import AiCallContext, run_ai_interaction
from collectai.ai_orchestration.prompts.builder import AllowedPromptContext
from collectai.ai_orchestration.prompts.intent_v1 import PROMPT_VERSION, build_intent_request
from collectai.ai_orchestration.safety_precedence import apply_safety_precedence
from collectai.ai_orchestration.schemas.intent import IntentResult
from collectai.application._chat_reply_planning import _sensitive_customer_message_reason
from collectai.audit import queries as audit_queries
from collectai.audit.service import AuditService
from collectai.config.policy.provider import PolicyProvider
from collectai.llm_provider.anthropic_live import AnthropicProvider
from collectai.llm_provider.base import LlmProvider, ProviderResult
from collectai.llm_provider.mock import MockProvider
from collectai.types.clock import Clock
from collectai.types.enums import EscalationReason, Intent, Persona, ProviderMode
from collectai.types.ids import EntityPrefix, generate_id
from collectai_eval.schemas import EvalCase, EvalCaseResult, EvalDataset, EvalRunResult, TokenUsage

_CAPABILITY = "EVAL_INTENT_CLASSIFICATION"
# A fixed, valid-shaped (real ULID-suffixed) customer/account id pair used
# as the AllowedPromptContext/audit-event subject for every case in every
# run -- no real customer or account ever exists at this id; evaluation
# never reads or writes a delinquency_record, so nothing needs it to.
_EVAL_CUSTOMER_ID = generate_id(EntityPrefix.CUSTOMER)
_EVAL_ACCOUNT_ID = generate_id(EntityPrefix.ACCOUNT)


class LiveEvalRefusedError(Exception):
    """AC3: LIVE mode was requested without the explicit flag, without an
    API key, or inside CI -- always fail closed, never silently fall back
    to MOCK."""


class LiveEvalCiRefusedError(LiveEvalRefusedError):
    def __init__(self) -> None:
        super().__init__(
            "LIVE evaluation is refused inside CI (the CI environment variable is set)."
        )


class LiveEvalNotConfirmedError(LiveEvalRefusedError):
    def __init__(self) -> None:
        super().__init__("LIVE evaluation requires live_confirmed=True (an explicit opt-in).")


class LiveEvalMissingApiKeyError(LiveEvalRefusedError):
    def __init__(self) -> None:
        super().__init__("LIVE evaluation requires a real ANTHROPIC_API_KEY.")


@dataclass(frozen=True, slots=True)
class RunConfig:
    mode: ProviderMode
    triggered_by: str
    live_confirmed: bool = False
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None


def _build_mock_provider(dataset: EvalDataset) -> MockProvider:
    """AC2: a plain, unscripted `MockProvider()` returns its fixed default
    (`"Acknowledged."`, a bare string) for every call -- not valid JSON
    against `IntentResult`'s schema, so every case would fail schema
    validation and MOCK mode could never show a passing case at all. This
    scripts the dataset's own expected answer for each case instead,
    in order: MOCK mode is a smoke test of the harness/scoring pipeline
    itself (schema validation, precedence, storage, metrics), proving it
    correctly recognizes a model that always answers correctly -- never a
    measure of a real model's accuracy (LIVE mode measures that)."""
    responses = [_expected_intent_response(case) for case in dataset.cases]
    return MockProvider(responses)


def _expected_intent_response(case: EvalCase) -> ProviderResult:
    payload = {
        "label": case.expected_intent,
        "confidence": 0.95,
        "rationale": "Matches the dataset's own expected label.",
        "vulnerability_detected": case.expected_vulnerability_detected,
        "vulnerability_category": case.expected_vulnerability_category,
        "vulnerability_rationale": (
            "Matches the dataset's own expected signal."
            if case.expected_vulnerability_detected
            else ""
        ),
        "special_request": case.expected_special_request,
    }
    return ProviderResult(
        content=json.dumps(payload), model_id="mock-eval-model", latency_ms=0.0
    )


def _build_provider(
    config: RunConfig, dataset: EvalDataset
) -> tuple[LlmProvider, str | None]:
    """Returns `(provider, model_id)`. `model_id` is `None` for MOCK (the
    `eval_run.model_id` column's own CHECK constraint: `mode = 'LIVE' OR
    model_id IS NULL`)."""
    if config.mode is ProviderMode.MOCK:
        return _build_mock_provider(dataset), None
    if os.environ.get("CI"):
        raise LiveEvalCiRefusedError
    if not config.live_confirmed:
        raise LiveEvalNotConfirmedError
    if not config.anthropic_api_key:
        raise LiveEvalMissingApiKeyError
    model = config.anthropic_model or "claude-REPLACE_ME"
    provider = AnthropicProvider(
        model_id=model,
        api_key=SecretStr(config.anthropic_api_key),
        timeout_seconds=20,
    )
    return provider, model


def _predicted_escalation_reason(intent_result: IntentResult) -> str | None:
    decision = apply_safety_precedence(intent_result)
    if intent_result.label is Intent.REQUEST_HUMAN:
        return EscalationReason.REQUEST_HUMAN.value
    if decision.sensitive:
        return _sensitive_customer_message_reason(intent_result).value
    return None


async def _run_one_case(
    session: AsyncSession,
    *,
    case: EvalCase,
    provider: LlmProvider,
    provider_mode: ProviderMode,
    audit_service: AuditService,
) -> tuple[EvalCaseResult, dict[str, int] | None]:
    correlation_id = f"eval-{uuid.uuid4().hex}"
    context = AllowedPromptContext(
        customer_display_name=_EVAL_CUSTOMER_ID, account_reference=_EVAL_ACCOUNT_ID
    )
    request = build_intent_request(context=context, message=case.message)
    call_context = AiCallContext(
        correlation_id=correlation_id,
        capability=_CAPABILITY,
        prompt_version=PROMPT_VERSION,
        provider_name="anthropic" if provider_mode is ProviderMode.LIVE else "mock",
        provider_mode=provider_mode,
        actor_persona=Persona.CUSTOMER,
        customer_id=_EVAL_CUSTOMER_ID,
        account_id=_EVAL_ACCOUNT_ID,
    )
    result = await run_ai_interaction(
        provider,
        request,
        IntentResult,
        call_context,
        audit_service,
        domain_port=None,
        retry_bound=1,
    )

    expected: dict[str, Any] = {
        "intent": case.expected_intent,
        "vulnerability_detected": case.expected_vulnerability_detected,
        "special_request": case.expected_special_request,
        "escalation_reason": case.expected_escalation_reason,
    }
    if result.structured_output is None or not result.governed:
        actual: dict[str, Any] = {
            "intent": None,
            "vulnerability_detected": None,
            "special_request": None,
            "escalation_reason": None,
            "governed": result.governed,
            "safe_state": result.safe_state.value,
        }
        passed = False
    else:
        intent_result = result.structured_output
        predicted_reason = _predicted_escalation_reason(intent_result)
        actual = {
            "intent": intent_result.label.value,
            "vulnerability_detected": intent_result.vulnerability_detected,
            "special_request": intent_result.special_request.value,
            "escalation_reason": predicted_reason,
            "governed": True,
            "safe_state": result.safe_state.value,
        }
        intent_ok = intent_result.label.value == case.expected_intent
        # AC5's "where applicable": only score escalation_reason when this
        # case's expected value is itself one this runner can predict
        # (REQUEST_HUMAN or a `decision.sensitive` case) -- never
        # UNRESOLVED_UNKNOWN/AMBIGUOUS_VALIDATION, which this module's own
        # docstring documents as state-dependent, not classification-level.
        scorable_reasons = {r.value for r in EscalationReason} - {
            EscalationReason.UNRESOLVED_UNKNOWN.value,
            EscalationReason.AMBIGUOUS_VALIDATION.value,
        }
        if case.expected_escalation_reason in scorable_reasons:
            reason_ok = predicted_reason == case.expected_escalation_reason
        else:
            reason_ok = True
        passed = intent_ok and reason_ok

    tokens = await _read_back_token_usage(session, correlation_id)
    critical_violation = _is_critical_violation(case, actual)
    case_result = EvalCaseResult(
        case_id=case.case_id,
        category=case.category,
        expected=expected,
        actual=actual,
        passed=passed,
        critical_policy_violation=critical_violation,
    )
    return case_result, tokens


def _is_critical_violation(case: EvalCase, actual: dict[str, Any]) -> bool:
    """AC-adjacent (data-models.md's own `critical_policy_violation` field
    docstring): true for a missed vulnerable-customer escalation -- the one
    failure mode severe enough to flag distinctly from an ordinary
    intent-label miss."""
    if not case.expected_vulnerability_detected:
        return False
    return actual.get("vulnerability_detected") is not True


async def _read_back_token_usage(
    session: AsyncSession, correlation_id: str
) -> dict[str, int] | None:
    events = await audit_queries.list_by_correlation_id(session, correlation_id)
    for event in events:
        if event.token_usage is not None:
            input_tokens = event.token_usage.get("input_tokens")
            output_tokens = event.token_usage.get("output_tokens")
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                return {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return None


async def run_eval(
    session: AsyncSession,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    dataset: EvalDataset,
    config: RunConfig,
    clock: Clock,
    policy_provider: PolicyProvider,
) -> EvalRunResult:
    """AC2/AC3/AC4: run every case in `dataset`, in MOCK or LIVE per
    `config.mode` (LIVE fails closed via `_build_provider` unless properly
    confirmed and outside CI), and return the aggregated `EvalRunResult`
    `collectai_eval.store.store_eval_run` persists. `session_factory` backs
    each case's own `AuditService.record` call (its own independent
    transaction, mirroring production's own "non-state-changing AI
    activity" pattern -- see `audit/service.py`'s module docstring);
    `session` is used only to read those now-committed audit rows back for
    token-usage accounting, and by the caller afterward to store the run."""
    provider, model_id = _build_provider(config, dataset)
    audit_service = AuditService(clock, session_factory)

    case_results: list[EvalCaseResult] = []
    total_input_tokens = 0
    total_output_tokens = 0
    any_tokens = False
    for case in dataset.cases:
        case_result, tokens = await _run_one_case(
            session,
            case=case,
            provider=provider,
            provider_mode=config.mode,
            audit_service=audit_service,
        )
        case_results.append(case_result)
        if tokens is not None:
            any_tokens = True
            total_input_tokens += tokens["input_tokens"]
            total_output_tokens += tokens["output_tokens"]

    from collectai_eval.metrics import compute_metrics

    metrics = compute_metrics(case_results)
    token_usage = (
        TokenUsage(input_tokens=total_input_tokens, output_tokens=total_output_tokens)
        if any_tokens
        else None
    )

    # `eval_run.policy_version` is NOT NULL and FKs to `policy_rule_set
    # .policy_version` (matching `escalation_case.routing_policy_version`'s
    # own real FK -- see migration 0009's finding). A placeholder string
    # would violate that FK, so this fails closed by propagating
    # `PolicyUnavailable` rather than fabricating one: evaluation is
    # meaningless without an active policy, since the deterministic
    # precedence rule this run measures depends on it.
    policy_version = policy_provider.get_active().policy_version

    return EvalRunResult(
        mode=config.mode.value,
        dataset_version=dataset.dataset_version,
        dataset_provenance=dataset.provenance,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        policy_version=policy_version,
        run_at=clock.now(),
        case_results=case_results,
        metrics=metrics,
        token_usage=token_usage,
        estimated_cost_usd=None,
        triggered_by=config.triggered_by,
    )
