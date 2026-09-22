"""Append-only audit (layer 3): `AuditService`, redaction, event drafts and
chain/filter read queries. Imports only `types`, `config` and `persistence`
(never `rules_engine`, AI packages or `api`) per
`specs/design/folder-structure.md` section 5.
"""

from __future__ import annotations
