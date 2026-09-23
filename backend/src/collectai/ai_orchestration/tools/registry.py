"""Closed six-tool registry and per-turn dispatch loop (E5-S4 AC1, AC2,
AC6-AC9).

`ToolName` is the closed set (AC1): `dispatch_tool_call` rejects anything
else as an unknown tool, and this enum is the one place a seventh tool name
could ever be added. `TurnToolCallBudget` is pure, mutable, in-memory
per-turn state (AC6-AC9) -- never persisted; the caller (a future
orchestrator/chat-flow story, E6-S1) constructs one per turn and passes it
into every `dispatch_tool_call` for that turn.

Order of checks in `dispatch_tool_call` (a deliberate judgment call -- see
this story's report): the per-turn cap is consumed FIRST, before the tool
name or its arguments are even looked at. `TOOL_CALL_CAP_PER_TURN` bounds
the number of tool-call *attempts* the model gets this turn, not just the
number of well-formed ones, so a model that spams malformed calls cannot
dodge it. Once the budget is exhausted, nothing past that point ever runs:
no rules-engine call, no idempotency read/write (AC8) -- only the
`TOOL_CAP_REACHED` audit event.

NOTE: this file is over the code-gen skill's 200-line block-threshold note
(the closed enum, budget dataclass, three outcome dataclasses and the
six-way dispatch helper each earn their place; nothing here is filler). If
it grows further, split the outcome dataclasses into their own module,
re-exported from `tools/__init__.py` so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ValidationError

from collectai.ai_orchestration.ports import ToolBackendPort
from collectai.ai_orchestration.tools.propose_tools import (
    call_escalate_to_human,
    call_flag_dispute,
    call_flag_hardship,
    call_propose_ptp,
)
from collectai.ai_orchestration.tools.read_tools import (
    call_get_account_context,
    call_get_eligible_options,
)
from collectai.audit.events import AuditEventDraft
from collectai.audit.service import AuditService
from collectai.types.enums import ActorKind, AuditStage

RawArgs = dict[str, object]

# Local constant (do NOT add to `audit.events`, per this story's brief -- a
# sibling story already extended that module this run). AC8.
TOOL_CAP_REACHED_EVENT_TYPE: Final[str] = "TOOL_CAP_REACHED"


class ToolName(StrEnum):
    """The closed set of six tools (AC1). No tool that mutates balances,
    payments, arrangements or case decisions directly is ever a member."""

    GET_ACCOUNT_CONTEXT = "get_account_context"
    GET_ELIGIBLE_OPTIONS = "get_eligible_options"
    PROPOSE_PTP = "propose_ptp"
    FLAG_HARDSHIP = "flag_hardship"
    FLAG_DISPUTE = "flag_dispute"
    ESCALATE_TO_HUMAN = "escalate_to_human"


READ_TOOLS: Final[frozenset[ToolName]] = frozenset(
    {ToolName.GET_ACCOUNT_CONTEXT, ToolName.GET_ELIGIBLE_OPTIONS}
)
PROPOSE_TOOLS: Final[frozenset[ToolName]] = frozenset(
    {
        ToolName.PROPOSE_PTP,
        ToolName.FLAG_HARDSHIP,
        ToolName.FLAG_DISPUTE,
        ToolName.ESCALATE_TO_HUMAN,
    }
)


@dataclass(slots=True)
class TurnToolCallBudget:
    """Mutable, in-memory per-turn tool-call counter, sized from
    `Settings.tool_call_cap_per_turn` (AC6: validated config, default 5,
    range 1-20 -- injected by the caller, never hard-coded here)."""

    cap: int
    _calls_made: int = field(default=0, init=False)

    def try_consume(self) -> bool:
        """Consume one call from the budget. Returns False (leaving the
        budget unchanged) once `cap` calls have already been consumed."""
        if self._calls_made >= self.cap:
            return False
        self._calls_made += 1
        return True

    @property
    def calls_made(self) -> int:
        return self._calls_made


@dataclass(frozen=True, slots=True)
class ToolSuccess:
    tool_name: ToolName
    result: BaseModel


@dataclass(frozen=True, slots=True)
class ToolError:
    """AC2: an unknown tool name (`tool_name=None`) or schema-invalid
    arguments (`tool_name` set) -- the tool never executed."""

    tool_name: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ToolCapReached:
    """AC7-AC9: the per-turn cap was already exhausted -- the tool never
    executed, and a `TOOL_CAP_REACHED` audit event was written (AC8)."""

    tool_name: str


ToolDispatchOutcome = ToolSuccess | ToolError | ToolCapReached


async def dispatch_tool_call(
    *,
    tool_name: str,
    raw_args: RawArgs,
    backend: ToolBackendPort,
    budget: TurnToolCallBudget,
    turn_id: str,
    customer_id: str,
    correlation_id: str,
    audit_service: AuditService,
) -> ToolDispatchOutcome:
    """Validate, budget-check and execute one tool call. Never raises past
    this boundary: an unknown tool name or invalid arguments becomes a
    `ToolError` (AC2), never an uncaught exception."""
    if not budget.try_consume():
        await _record_cap_reached(audit_service, correlation_id, customer_id, tool_name)
        return ToolCapReached(tool_name=tool_name)

    try:
        parsed_name = ToolName(tool_name)
    except ValueError:
        return ToolError(tool_name=None, message=f"Unknown tool: {tool_name!r}")

    try:
        result = await _execute(parsed_name, raw_args, customer_id, turn_id, backend)
    except ValidationError as exc:
        return ToolError(tool_name=parsed_name.value, message=str(exc))

    return ToolSuccess(tool_name=parsed_name, result=result)


async def _execute(
    tool_name: ToolName,
    raw_args: RawArgs,
    customer_id: str,
    turn_id: str,
    backend: ToolBackendPort,
) -> BaseModel:
    """One branch per closed-set member (AC1); the six-way dispatch is kept
    as plain `if`/`return` rather than a lookup dict so mypy can see every
    branch returns a `BaseModel` without a cast."""
    if tool_name is ToolName.GET_ACCOUNT_CONTEXT:
        return await call_get_account_context(raw_args, customer_id=customer_id, backend=backend)
    if tool_name is ToolName.GET_ELIGIBLE_OPTIONS:
        return await call_get_eligible_options(raw_args, customer_id=customer_id, backend=backend)
    if tool_name is ToolName.PROPOSE_PTP:
        return await call_propose_ptp(
            raw_args,
            customer_id=customer_id,
            turn_id=turn_id,
            tool_name=tool_name.value,
            backend=backend,
        )
    if tool_name is ToolName.FLAG_HARDSHIP:
        return await call_flag_hardship(
            raw_args,
            customer_id=customer_id,
            turn_id=turn_id,
            tool_name=tool_name.value,
            backend=backend,
        )
    if tool_name is ToolName.FLAG_DISPUTE:
        return await call_flag_dispute(
            raw_args,
            customer_id=customer_id,
            turn_id=turn_id,
            tool_name=tool_name.value,
            backend=backend,
        )
    return await call_escalate_to_human(
        raw_args,
        customer_id=customer_id,
        turn_id=turn_id,
        tool_name=tool_name.value,
        backend=backend,
    )


async def _record_cap_reached(
    audit_service: AuditService, correlation_id: str, customer_id: str, tool_name: str
) -> None:
    await audit_service.record(
        AuditEventDraft(
            correlation_id=correlation_id,
            stage=AuditStage.RULE_VALIDATION,
            event_type=TOOL_CAP_REACHED_EVENT_TYPE,
            actor_kind=ActorKind.AI,
            customer_id=customer_id,
            final_action="TOOL_CALL_BLOCKED",
            resource_type="tool_call",
            resource_id=tool_name,
        )
    )
