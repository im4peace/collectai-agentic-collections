"""Persistence layer (layer 2): PostgreSQL access.

May import `collectai.types` and `collectai.config` only (folder-structure.md
section 5). Must never import `audit`, `rules_engine`, `ai_orchestration`,
`api`, or any higher layer.
"""

from __future__ import annotations
