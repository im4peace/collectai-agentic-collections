"""`GET /api/portfolio` (api-contracts.md 3.3): delinquent accounts with
deterministic priority, filter and sort. COLLECTIONS_OFFICER only.

NOTE -- PolicyProvider wiring: `api/app.py`'s `create_app`/`lifespan` does
not yet build or store a `PolicyProvider` on `app.state` (no story before
E3-S2 in this parallel Group E run has needed one from a router, and this
file must not edit `app.py`, which the orchestrator wires up once every
sibling story lands). `get_policy_provider` below reads
`request.app.state.policy_provider` when a later story adds it there, and
otherwise falls back to a process-wide `PolicyProvider` loaded from the
same seed policy file `bootstrap/main.py` activates at real startup --
so this endpoint has a real, working active policy either way. Tests force
the fail-closed 503 path with a FastAPI `dependency_overrides` entry for
`get_policy_provider` (see `tests/api/test_e3_s2_portfolio_filter_sort.py`).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from collectai.api.deps import AuditServiceDep, DbSession, PersonaContext, require_capability
from collectai.api.middleware.errors import (
    PolicyUnavailableError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.schemas.portfolio import PageInfo, PortfolioItem, PortfolioPage
from collectai.config.policy.loader import SEED_POLICY_V1_VERSION, load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services.portfolio_service import PortfolioPageResult, list_portfolio
from collectai.types.clock import SystemClock
from collectai.types.enums import CollectionStatus, PriorityBand
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

_require_portfolio_read = require_capability("portfolio:read")
_fallback_policy_provider: PolicyProvider | None = None


def _build_fallback_policy_provider() -> PolicyProvider:
    """A process-wide `PolicyProvider` activated from the same seed file
    `bootstrap.main.run_startup_validation` uses at real startup, for when
    nothing has put one on `app.state` yet (see module docstring). Building
    fails the same way real startup does (`PolicyFileNotFoundError`/
    `PolicyValidationError`), not silently -- it never returns a provider
    with no active version by accident."""
    clock = SystemClock()
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate(SEED_POLICY_V1_VERSION, clock)
    return provider


def get_policy_provider(request: Request) -> PolicyProvider:
    configured = getattr(request.app.state, "policy_provider", None)
    if isinstance(configured, PolicyProvider):
        return configured
    global _fallback_policy_provider
    if _fallback_policy_provider is None:
        _fallback_policy_provider = _build_fallback_policy_provider()
    return _fallback_policy_provider


PolicyProviderDep = Annotated[PolicyProvider, Depends(get_policy_provider)]


@router.get("", response_model=PortfolioPage, openapi_extra={"x-capability": "portfolio:read"})
async def get_portfolio(
    request: Request,
    db: DbSession,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    persona_context: PersonaContext = Depends(_require_portfolio_read),  # noqa: B008
    dpd_min: Annotated[int | None, Query(ge=0)] = None,
    dpd_max: Annotated[int | None, Query(ge=0)] = None,
    priority_band: Annotated[list[PriorityBand] | None, Query()] = None,
    status: Annotated[list[CollectionStatus] | None, Query()] = None,
    sort_by: Literal["overdue_amount", "dpd", "priority_score"] = "priority_score",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PortfolioPage:
    """AC1-AC4: deterministic-priority portfolio list, filtered by DPD
    range/priority band/status (AND across parameters) and sorted by
    overdue amount, DPD or priority score."""
    _validate_dpd_range(dpd_min, dpd_max)
    result = await list_portfolio(
        db,
        policy_provider=policy_provider,
        audit_service=audit_service,
        correlation_id=resolve_correlation_id(request),
        dpd_min=dpd_min,
        dpd_max=dpd_max,
        statuses=status,
        priority_bands=priority_band,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    if not result.ok:
        assert result.failure is not None  # noqa: S101 - narrows for mypy after `.ok` check
        raise PolicyUnavailableError(message=result.failure.message)
    assert result.value is not None  # noqa: S101 - narrows for mypy after `.ok` check
    return _to_portfolio_page(result.value, limit=limit, offset=offset)


def _validate_dpd_range(dpd_min: int | None, dpd_max: int | None) -> None:
    if dpd_min is not None and dpd_max is not None and dpd_max < dpd_min:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.FIELD_INVALID,
            message="dpd_max must be greater than or equal to dpd_min.",
        )


def _to_portfolio_page(page: PortfolioPageResult, *, limit: int, offset: int) -> PortfolioPage:
    return PortfolioPage(
        items=[
            PortfolioItem(
                account_id=row.account_id,
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                account_type=row.account_type,
                outstanding_balance=row.outstanding_balance,
                overdue_amount=row.overdue_amount,
                dpd=row.dpd,
                bucket=row.bucket,
                collection_status=row.collection_status,
                priority_band=row.priority_band,
                priority_score=format(row.priority_score, "f"),
                human_treatment=row.human_treatment,
                automated_treatment_suppressed=row.automated_treatment_suppressed,
                record_version=row.record_version,
            )
            for row in page.items
        ],
        page=PageInfo(limit=limit, offset=offset, total=page.total),
        policy_version=page.policy_version,
    )


__all__ = ["get_policy_provider", "router"]
