"""Standalone, CLI-invokable batch jobs (layer 8, alongside `bootstrap`).

Each module here is a thin orchestration wrapper around a real
`domain_services` function: it owns process wiring (engine, session,
`AuditService`, `PolicyProvider`, transaction boundary) only, never business
logic. `rules_engine` and `ai_orchestration` both list `collectai.jobs` in
their `.importlinter` forbidden-imports set, so nothing below layer 5 may
ever import a job -- jobs call down, never the reverse.
"""

from __future__ import annotations
