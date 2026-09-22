"""Domain services: layer 5a orchestration over `rules_engine` + `persistence`.

The first module in this package is `snapshot_service` (E2-S5). Per the
layering rule (specs/design/folder-structure.md section 5), `domain_services`
may import `types`, `config`, `rules_engine` and `persistence`, but never
`audit`, `ai_orchestration`, `llm_provider`, `api` or `application`.
"""

from __future__ import annotations
