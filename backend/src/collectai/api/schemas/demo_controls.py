"""Dev and demo control wire schemas (E9-S3; api-contracts.md 3.14, section
4: `DemoState`, `ClockAdvanceRequest`, `ClockAdvanceResult`,
`LifecycleRunResult`, `SimulatePaymentRequest`, `SimulatePaymentResult`,
`ReseedRequest`, `ReseedResult`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from collectai.api.schemas.me import PaymentEvent, PromiseToPay
from collectai.types.enums import ClockMode, LlmMode, PaymentOutcome

_MONEY_INPUT_PATTERN = r"^-?\d+(\.\d+)?$"


class ClockInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ClockMode
    current_time: str


class DemoState(BaseModel):
    model_config = ConfigDict(frozen=True)

    llm_mode: LlmMode
    clock: ClockInfo
    demo_controls_enabled: bool
    policy_version: str | None


class ClockAdvanceRequest(BaseModel):
    """Unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: int = Field(ge=1, le=365)
    refresh_snapshots: bool = True


class ClockAdvanceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    clock: ClockInfo
    snapshots_refreshed: int


class LifecycleRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluated: int
    kept: int
    broken: int
    unchanged: int


class SimulatePaymentRequest(BaseModel):
    """Unknown fields are rejected. `amount` is a loosely-shaped decimal
    string (mirrors `api.schemas.ptps.MoneyInput`'s own rationale): only a
    genuinely malformed string is a schema `FIELD_INVALID` error, so
    `ZERO_AMOUNT`/`NEGATIVE_AMOUNT`/`OVER_PRECISION`/`OVER_BALANCE` stay
    deterministic `BUSINESS_RULE_VIOLATION` outcomes `demo_service` raises,
    not schema-layer rejections."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    amount: str = Field(pattern=_MONEY_INPUT_PATTERN, max_length=32)
    outcome: PaymentOutcome = PaymentOutcome.SUCCEEDED


class SimulatePaymentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    payment_event: PaymentEvent
    ptp: PromiseToPay | None
    replayed: bool = False


class ReseedRequest(BaseModel):
    """Unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confirm: bool


class ReseedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    customers: int
    accounts: int
    delinquency_records: int
    delinquent_items: int
    interactions: int
    promise_to_pays: int
