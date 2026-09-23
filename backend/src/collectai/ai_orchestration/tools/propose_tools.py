"""PROPOSE tool wrappers (E5-S4 AC2, AC3, AC4): schema-validate raw args,
derive the deterministic idempotency key from `(turn_id, tool_name,
canonical arguments)`, and call the injected `ToolBackendPort`. No business
logic and no persistence here -- see `application/tool_backend.py` and
`domain_services/idempotency.py`.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from collectai.ai_orchestration.ports import ToolBackendPort
from collectai.ai_orchestration.schemas.tool_args import (
    EscalateToHumanArgs,
    FlagDisputeArgs,
    FlagHardshipArgs,
    ProposePtpArgs,
)
from collectai.ai_orchestration.schemas.tool_results import (
    EscalateToHumanResult,
    FlagDisputeResult,
    FlagHardshipResult,
    ProposePtpResult,
)

RawArgs = dict[str, object]


def compute_idempotency_key(turn_id: str, tool_name: str, args: BaseModel) -> str:
    """`sha256(f"{turn_id}:{tool_name}:{canonical_json(args)}")`
    (AC3; data-models.md section 4.5). Deterministic and never
    client-supplied: two identical PROPOSE calls in the same turn always
    produce the same key, so a model retry replays the original result
    instead of creating a second proposal.
    """
    canonical_json = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest_input = f"{turn_id}:{tool_name}:{canonical_json}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


async def call_propose_ptp(
    raw_args: RawArgs,
    *,
    customer_id: str,
    turn_id: str,
    tool_name: str,
    backend: ToolBackendPort,
) -> ProposePtpResult:
    args = ProposePtpArgs.model_validate(raw_args)
    key = compute_idempotency_key(turn_id, tool_name, args)
    return await backend.propose_ptp(customer_id, key, args)


async def call_flag_hardship(
    raw_args: RawArgs,
    *,
    customer_id: str,
    turn_id: str,
    tool_name: str,
    backend: ToolBackendPort,
) -> FlagHardshipResult:
    args = FlagHardshipArgs.model_validate(raw_args)
    key = compute_idempotency_key(turn_id, tool_name, args)
    return await backend.flag_hardship(customer_id, key, args)


async def call_flag_dispute(
    raw_args: RawArgs,
    *,
    customer_id: str,
    turn_id: str,
    tool_name: str,
    backend: ToolBackendPort,
) -> FlagDisputeResult:
    args = FlagDisputeArgs.model_validate(raw_args)
    key = compute_idempotency_key(turn_id, tool_name, args)
    return await backend.flag_dispute(customer_id, key, args)


async def call_escalate_to_human(
    raw_args: RawArgs,
    *,
    customer_id: str,
    turn_id: str,
    tool_name: str,
    backend: ToolBackendPort,
) -> EscalateToHumanResult:
    args = EscalateToHumanArgs.model_validate(raw_args)
    key = compute_idempotency_key(turn_id, tool_name, args)
    return await backend.escalate_to_human(customer_id, key, args)
