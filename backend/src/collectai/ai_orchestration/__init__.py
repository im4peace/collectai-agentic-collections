"""AI orchestration (layer 5b): prompt assembly from an allow-list, the
post-generation grounding check, and template fallbacks. Imports only
`types`, `config` and `llm_provider` -- never `rules_engine`,
`domain_services`, `persistence` or `api` (folder-structure.md section 5).
"""

from __future__ import annotations
