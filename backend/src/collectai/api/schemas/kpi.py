"""KPI wire schemas (E10-S3; api-contracts.md 3.13, section "Kpi",
"AiQualityKpis", "KpiResponse", "EvalRunSummary", "EvalRunPage").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import ClaimStatus, DataLabel, KpiUnit, Persona, ProviderMode


class PageInfo(BaseModel):
    """Offset pagination block (api-contracts.md `PageInfo`)."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int
    total: int


class Kpi(BaseModel):
    """One KPI with definition and label (api-contracts.md `Kpi`)."""

    model_config = ConfigDict(frozen=True)

    kpi_id: str
    name: str
    definition: str
    formula: str
    data_label: DataLabel
    owner_persona: Persona
    unit: KpiUnit
    value: str | None
    numerator: str | None
    denominator: str | None
    sample_size: int | None
    claim_status: ClaimStatus
    target: str | None
    source_note: str | None


class AiQualityKpis(BaseModel):
    """AI KPIs, MOCK and LIVE never mixed (api-contracts.md `AiQualityKpis`)."""

    model_config = ConfigDict(frozen=True)

    mock: list[Kpi]
    live: list[Kpi]
    live_run_available: bool
    note: str


class KpiResponse(BaseModel):
    """KPI tree (BRD 4.5). Deferred KPIs are absent (api-contracts.md
    `KpiResponse`)."""

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    policy_version: str | None
    business: list[Kpi]
    operational: list[Kpi]
    ai_quality: AiQualityKpis


class EvalRunSummary(BaseModel):
    """Stored EvalRun (api-contracts.md `EvalRunSummary`)."""

    model_config = ConfigDict(frozen=True)

    eval_run_id: str
    mode: ProviderMode
    dataset_version: str
    model_id: str | None
    prompt_version: str
    policy_version: str
    run_at: datetime
    case_count: int
    intent_accuracy: str | None
    estimated_cost_usd: str | None


class EvalRunPage(BaseModel):
    """Eval runs, newest first (api-contracts.md `EvalRunPage`)."""

    model_config = ConfigDict(frozen=True)

    items: list[EvalRunSummary]
    page: PageInfo
