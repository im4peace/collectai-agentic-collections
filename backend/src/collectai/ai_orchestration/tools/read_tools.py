"""READ tool wrappers (E5-S4 AC1, AC2, AC5): schema-validate raw args, then
call the injected `ToolBackendPort`. Pure dispatch glue only -- no business
logic and no persistence here; that lives behind the Protocol in
`application/tool_backend.py`.
"""

from __future__ import annotations

from collectai.ai_orchestration.ports import ToolBackendPort
from collectai.ai_orchestration.schemas.tool_args import (
    GetAccountContextArgs,
    GetEligibleOptionsArgs,
)
from collectai.ai_orchestration.schemas.tool_results import (
    AccountContextResult,
    EligibleOptionsResult,
)

RawArgs = dict[str, object]


async def call_get_account_context(
    raw_args: RawArgs, *, customer_id: str, backend: ToolBackendPort
) -> AccountContextResult:
    """Raises `pydantic.ValidationError` on invalid/unknown args (AC2);
    `registry.dispatch_tool_call` is the only caller expected to catch it."""
    args = GetAccountContextArgs.model_validate(raw_args)
    return await backend.get_account_context(customer_id, args)


async def call_get_eligible_options(
    raw_args: RawArgs, *, customer_id: str, backend: ToolBackendPort
) -> EligibleOptionsResult:
    args = GetEligibleOptionsArgs.model_validate(raw_args)
    return await backend.get_eligible_options(customer_id, args)
