"""Intent classification schema (E6-S1 AC2, AC3).

`IntentResult` is the LLM's *advisory* interpretation of one customer chat
message -- never authoritative (CLAUDE.md's core engineering principle: the
LLM classifies, it never decides a financial action). It feeds
`ai_orchestration.orchestrator.run_ai_interaction(..., domain_port=None)`
exactly like every other advisory schema (E5-S2's `finish_advisory` path),
and `ai_orchestration.safety_precedence.apply_safety_precedence` is the one
deterministic, non-LLM function that decides what happens next (D-016).

`label` is restricted to `Intent`'s seven members (AC2): a schema-invalid
label such as `VULNERABLE_CUSTOMER` fails Pydantic enum validation before it
ever reaches `apply_safety_precedence` -- "vulnerability" is carried instead
by the separate `vulnerability_detected`/`vulnerability_category`/
`vulnerability_rationale` advisory safety signals (AC3), never as an eighth
intent label.

Design choice -- `vulnerability_rationale` optionality: this field defaults
to `""` (always present, never `None`) rather than `str | None = None`. The
field is only ever *meaningful* when `vulnerability_detected` is `True`; an
empty string keeps the shape uniform (every `IntentResult` has a `str` here,
never a `None` a caller must guard against) while still making "no
rationale supplied" unambiguous. `rationale` (the intent-label rationale)
has no default since it is always meaningful.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from collectai.ai_orchestration.schemas._base import StrictToolModel
from collectai.types.enums import Intent, SpecialRequest, VulnerabilityCategory

_Rationale = Annotated[str, Field(min_length=1, max_length=500)]
_VulnerabilityRationale = Annotated[str, Field(max_length=500)]


class IntentResult(StrictToolModel):
    """Schema-validated intent classification plus advisory safety signals
    (AC2, AC3). `extra="forbid"` (via `StrictToolModel`) rejects any
    unrecognized key -- e.g. a model attempting to smuggle its own
    `proposal`/`action` field -- rather than silently dropping it."""

    label: Intent
    confidence: float = Field(ge=0, le=1)
    rationale: _Rationale
    vulnerability_detected: bool
    vulnerability_category: VulnerabilityCategory | None = None
    vulnerability_rationale: _VulnerabilityRationale = ""
    special_request: SpecialRequest
