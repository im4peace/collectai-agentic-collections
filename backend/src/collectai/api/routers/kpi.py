"""KPI endpoints (E10-S3; api-contracts.md 3.13): `GET /api/kpis`,
`GET /api/kpis/eval-runs`. Read-only, COLLECTIONS_MANAGER only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from collectai.api.deps import (
    ClockDep,
    DbSession,
    PersonaContext,
    PolicyProviderDep,
    require_capability,
)
from collectai.api.routers.me_ownership import LimitQuery, OffsetQuery
from collectai.api.schemas.kpi import (
    AiQualityKpis,
    EvalRunPage,
    EvalRunSummary,
    Kpi,
    KpiResponse,
    PageInfo,
)
from collectai.domain_services.kpi_service import (
    AiQualityKpiRows,
    KpiRow,
    compute_kpi_tree,
    list_eval_runs,
)
from collectai.types.enums import ProviderMode

router = APIRouter(prefix="/api/kpis", tags=["KPI"])

_KPI_READ = {"x-capability": "kpi:read"}
_require_kpi_read = require_capability("kpi:read")


def _kpi_view(row: KpiRow) -> Kpi:
    return Kpi(
        kpi_id=row.kpi_id,
        name=row.name,
        definition=row.definition,
        formula=row.formula,
        data_label=row.data_label,
        owner_persona=row.owner_persona,
        unit=row.unit,
        value=row.value,
        numerator=row.numerator,
        denominator=row.denominator,
        sample_size=row.sample_size,
        claim_status=row.claim_status,
        target=row.target,
        source_note=row.source_note,
    )


def _ai_quality_view(rows: AiQualityKpiRows) -> AiQualityKpis:
    return AiQualityKpis(
        mock=[_kpi_view(row) for row in rows.mock],
        live=[_kpi_view(row) for row in rows.live],
        live_run_available=rows.live_run_available,
        note=rows.note,
    )


@router.get("", response_model=KpiResponse, openapi_extra=_KPI_READ)
async def get_kpis(
    db: DbSession,
    clock: ClockDep,
    policy_provider: PolicyProviderDep,
    persona_context: Annotated[PersonaContext, Depends(_require_kpi_read)],
) -> KpiResponse:
    """AC1-AC6: the full KPI tree, COLLECTIONS_MANAGER only (`kpi:read`,
    AC5)."""
    del persona_context
    tree = await compute_kpi_tree(db, clock=clock, policy_provider=policy_provider)
    return KpiResponse(
        generated_at=tree.generated_at,
        policy_version=tree.policy_version,
        business=[_kpi_view(row) for row in tree.business],
        operational=[_kpi_view(row) for row in tree.operational],
        ai_quality=_ai_quality_view(tree.ai_quality),
    )


@router.get("/eval-runs", response_model=EvalRunPage, openapi_extra=_KPI_READ)
async def get_eval_runs(
    db: DbSession,
    persona_context: Annotated[PersonaContext, Depends(_require_kpi_read)],
    mode: ProviderMode | None = None,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> EvalRunPage:
    """Stored `EvalRun`s behind the AI KPIs, newest first."""
    del persona_context
    rows, total = await list_eval_runs(
        db, mode=mode.value if mode is not None else None, limit=limit, offset=offset
    )
    items = [
        EvalRunSummary(
            eval_run_id=row.eval_run_id,
            mode=ProviderMode(row.mode),
            dataset_version=row.dataset_version,
            model_id=row.model_id,
            prompt_version=row.prompt_version,
            policy_version=row.policy_version,
            run_at=row.run_at,
            case_count=row.case_count,
            intent_accuracy=row.intent_accuracy,
            estimated_cost_usd=row.estimated_cost_usd,
        )
        for row in rows
    ]
    return EvalRunPage(items=items, page=PageInfo(limit=limit, offset=offset, total=total))
