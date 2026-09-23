"""Wire models for the Promise-to-Pay endpoints this story owns
(api-contracts.md 3.6, section 4): `PtpValidateRequest`, `PtpValidationResult`,
`PtpCreateRequest`, `PromiseToPay` (response, named `PromiseToPayResponse`
here to avoid clashing with `types.models.promise_to_pay.PromiseToPay`, the
domain model these wire models are deliberately kept separate from -- the
API response additionally needs `remaining_amount`, a derived field, and
Z-suffixed timestamp strings, api-contracts.md 1.1's format).

`promised_amount` is typed as a loosely-shaped decimal string (`MoneyInput`),
not `types.money.Money`: `Money`'s own Pydantic validator rejects a negative,
zero or over-precision amount immediately as a schema `FIELD_INVALID` error,
which would pre-empt `rules_engine.ptp_rules.validate_ptp` ever seeing those
values -- but api-contracts.md's `POST /api/ptps` error list makes
`ZERO_AMOUNT`/`NEGATIVE_AMOUNT`/`OVER_PRECISION` deterministic
`BUSINESS_RULE_VIOLATION` (422) outcomes, not schema validation errors. Only
a genuinely malformed string (not a plain decimal at all) is rejected here,
at the schema layer, as `FIELD_INVALID`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from collectai.types.enums import Persona, PtpSource, PtpStatus
from collectai.types.ids import EntityPrefix, is_valid_id
from collectai.types.reason_codes import ReasonCode

_MONEY_INPUT_PATTERN = r"^-?\d+(\.\d+)?$"
MoneyInput = Annotated[str, Field(pattern=_MONEY_INPUT_PATTERN, max_length=32)]


def _validate_account_id(value: str) -> str:
    if not is_valid_id(value, EntityPrefix.ACCOUNT):
        raise ValueError("account_id must be a valid acc_ id.")
    return value


def _validate_item_id(value: str) -> str:
    if not is_valid_id(value, EntityPrefix.ITEM):
        raise ValueError("item_id must be a valid itm_ id.")
    return value


def _validate_interaction_reference(value: str) -> str:
    if is_valid_id(value, EntityPrefix.INTERACTION) or is_valid_id(
        value, EntityPrefix.CONVERSATION
    ):
        return value
    raise ValueError("interaction_reference must be a valid int_ or conv_ id.")


def _validate_ptp_id(value: str) -> str:
    if not is_valid_id(value, EntityPrefix.PROMISE_TO_PAY):
        raise ValueError("ptp_id must be a valid ptp_ id.")
    return value


AccountIdField = Annotated[str, AfterValidator(_validate_account_id)]
ItemIdField = Annotated[str, AfterValidator(_validate_item_id)]
InteractionReferenceField = Annotated[str, AfterValidator(_validate_interaction_reference)]
PtpIdField = Annotated[str, AfterValidator(_validate_ptp_id)]


class PtpValidateRequest(BaseModel):
    """Dry-run PTP validation (api-contracts.md 4). Unknown fields rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: AccountIdField
    promised_amount: MoneyInput
    promised_date: date


class PtpValidationResult(BaseModel):
    """Deterministic validation result (`POST /api/ptps/validate`, always 200)."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    reason_codes: list[ReasonCode]
    alternatives: dict[str, Any] | None
    policy_version: str


class PtpCreateRequest(BaseModel):
    """Officer manual PTP (D-040, api-contracts.md 4). Unknown fields rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: AccountIdField
    promised_amount: MoneyInput
    promised_date: date
    interaction_reference: InteractionReferenceField | None = None
    item_id: ItemIdField | None = None
    record_version: int = Field(ge=1)
    snapshot_as_of: datetime


class PromiseToPayResponse(BaseModel):
    """`PromiseToPay` (api-contracts.md section 4): the officer-facing view
    returned by `POST /api/ptps` and `GET /api/ptps/{ptp_id}`. Always built
    via `model_validate` from `domain_services.ptp_service.ptp_wire_dict`'s
    already wire-shaped dict, never constructed field-by-field here, so a
    fresh create and an idempotent replay serialize identically."""

    model_config = ConfigDict(frozen=True)

    ptp_id: PtpIdField
    account_id: AccountIdField
    promised_amount: str
    promised_date: date
    status: PtpStatus
    cumulative_paid: str
    remaining_amount: str
    interaction_reference: str | None
    source: PtpSource
    created_by_persona: Persona
    created_at: str
    updated_at: str
    kept_at: str | None
    broken_at: str | None
    cancelled_at: str | None
    cancel_reason: str | None
    policy_version: str
    version: int
