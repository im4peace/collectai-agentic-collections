"""Wire models for `GET /api/portfolio` (api-contracts.md 3.3, section 4:
`PageInfo`, `PortfolioItem`, `PortfolioPage`).

`PageInfo` has no other owner yet in this codebase (no story before E3-S2
in this parallel Group E run has created a shared pagination model), so it
is defined here, next to its only current user. A later story that adds
its own paginated list is expected to define its own `PageInfo`-shaped
model the same way `api/schemas/session.py` does for its own response
models, rather than import this one -- `api/schemas/portfolio.py` is not a
shared module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import AccountType, Bucket, CollectionStatus, PriorityBand
from collectai.types.money import Money


class PageInfo(BaseModel):
    """Offset pagination block (api-contracts.md `PageInfo`)."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int
    total: int


class PortfolioItem(BaseModel):
    """One delinquent account row (api-contracts.md `PortfolioItem`)."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    customer_id: str
    customer_name: str
    account_type: AccountType
    outstanding_balance: Money
    overdue_amount: Money
    dpd: int
    bucket: Bucket
    collection_status: CollectionStatus
    priority_band: PriorityBand
    priority_score: str
    human_treatment: bool
    automated_treatment_suppressed: bool
    record_version: int


class PortfolioPage(BaseModel):
    """Portfolio list (`GET /api/portfolio` response, api-contracts.md
    `PortfolioPage`)."""

    model_config = ConfigDict(frozen=True)

    items: list[PortfolioItem]
    page: PageInfo
    policy_version: str
