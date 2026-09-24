"""Pure data shapes for the evaluation framework (E10-S1), decoupled from
`collectai.ai_orchestration.schemas.intent.IntentResult` so this package's
own on-disk dataset/report shapes never silently change if that production
schema does -- a mismatch surfaces as an explicit mapping bug here, not a
quiet drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    category: str
    message: str
    expected_intent: str
    expected_vulnerability_detected: bool
    expected_vulnerability_category: str | None
    expected_special_request: str
    expected_escalation_reason: str | None


@dataclass(frozen=True, slots=True)
class EvalDataset:
    dataset_version: str
    provenance: dict[str, str]
    cases: list[EvalCase]


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    case_id: str
    category: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    passed: bool
    critical_policy_violation: bool


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class EvalRunResult:
    """One complete run's outcome -- `collectai_eval.store.store_eval_run`'s
    input, and what `collectai_eval.report.render_report` renders."""

    mode: str
    dataset_version: str
    dataset_provenance: dict[str, str]
    model_id: str | None
    prompt_version: str
    policy_version: str
    run_at: datetime
    case_results: list[EvalCaseResult]
    metrics: dict[str, Any]
    token_usage: TokenUsage | None
    estimated_cost_usd: float | None
    triggered_by: str
    case_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_count", len(self.case_results))
