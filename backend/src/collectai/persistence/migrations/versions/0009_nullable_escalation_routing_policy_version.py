"""Make escalation_case.routing_policy_version nullable (Group H finding,
found implementing E8-S1 AC4).

`escalation_case.routing_policy_version` FKs to `policy_rule_set
.policy_version` (migration 0006's `_add_policy_version_fks`) and was NOT
NULL. `domain_services.escalation_service._insert_case` fell back to a
literal placeholder string, `"POLICY_UNAVAILABLE"`, whenever `route_escalation`
returned no real version (its own AC5 policy-unavailable fallback) -- but
that placeholder was never itself a row in `policy_rule_set`, so the INSERT
always violated the FK. This has been true since E7-S1 first shipped
`create_escalation`; it was never caught because no existing test combined
"no active policy" with "an escalation must still be created" against a
real, FK-enforced Postgres database (every PolicyUnavailable-driven
escalation test used a policy that was merely stale/pending re-check, never
truly absent). E8-S1 AC4 (an arrangement rules-engine failure escalates
AMBIGUOUS_VALIDATION) is the first scenario that actually exercises this
combination.

The correct representation is NULL, not a fake row: `routing_flags`
containing `"POLICY_UNAVAILABLE"` already carries this signal (escalation_
service.py's own docstring: "the real signal a reader should key off, never
this placeholder string") -- the column only needed a value to satisfy a
constraint its own author did not realize was unsatisfiable via FK. Making
it nullable lets `escalation_service.py` pass `routing.policy_version`
through unchanged (`None` when unavailable) instead of substituting a
fictitious version.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE escalation_case ALTER COLUMN routing_policy_version DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE escalation_case ALTER COLUMN routing_policy_version SET NOT NULL")
