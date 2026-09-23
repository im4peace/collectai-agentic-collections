"""Shared strict-model base for every tool argument and result schema
(E5-S4). `extra="forbid"` is what makes AC2 ("invalid arguments returns a
tool error") and AC4 (`escalate_to_human` rejects a `queue`/`reviewer_role`
key rather than silently dropping it) hold for every schema uniformly, and
`frozen=True` matches every other value-object model in this codebase
(e.g. `config.policy.models._StrictModel`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictToolModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
