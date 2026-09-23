"""`application`: the layer that implements the AI orchestration seams
(`ai_orchestration.ports.DomainWritePort`, `ToolBackendPort`) against real
`rules_engine`, `domain_services` and `persistence` calls. `ai_orchestration`
itself never imports this package or the layers it wires together; only
`application` imports both sides.
"""

from __future__ import annotations
