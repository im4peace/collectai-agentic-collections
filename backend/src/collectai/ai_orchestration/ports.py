"""Protocols the `application` layer implements for `orchestrator.py`
(E5-S2; BRD 10.3's "authorization/policy validation -> deterministic domain
service -> permitted state transition" steps).

`ai_orchestration` must never import `domain_services` or `rules_engine`
directly (folder-structure.md layer 5b). `DomainWritePort` is the seam: a
later story's `application` layer implements it, wrapping a real
domain-service call, and hands the implementation to
`orchestrator.run_ai_interaction` -- this package only ever calls the
Protocol, never a concrete domain service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel, contravariant=True)


@dataclass(frozen=True, slots=True)
class DomainWriteOutcome:
    """What happened when validated, schema-conformant AI output was
    handed to the domain layer for authorization, policy validation and
    (if permitted) a state transition.

    `applied=False` covers every rejection the deterministic layer can make
    -- an authorization denial, a policy conflict (AC3), a business-rule
    violation -- uniformly: the model's proposal never became a state
    change, `rule_results`/`reason_code` say why, and the caller (BRD 10.5)
    still must not let the model's own words override that outcome.
    """

    applied: bool
    reason_code: str | None
    rule_results: dict[str, object] | None
    final_action: str | None
    resource_type: str | None
    resource_id: str | None


class DomainWritePort(Protocol[SchemaT]):
    """Implemented by the `application` layer for one kind of validated AI
    output. `apply` alone is trusted to perform authorization, policy
    validation, the deterministic domain-service call and -- only when it
    results in an actual state transition -- writing that transition's own
    audit event in the same unit of work (data-models.md AuditEvent: "written
    in the same transaction as the state transition it describes"). When
    `apply` returns `applied=False`, `orchestrator.py` writes the
    non-state-changing audit event itself; it never re-derives or second
    -guesses the outcome `apply` returned.
    """

    async def apply(self, structured_output: SchemaT) -> DomainWriteOutcome: ...
