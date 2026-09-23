"""Static role x capability authorization matrix (E3-S1 AC1, AC3-AC5;
api-contracts.md sections 1.5, 1.7).

Every non-public route declares exactly one capability string; this module
is the single source of truth for which of the four personas that
capability is granted to. It has no I/O and no FastAPI dependency of its
own -- `api/deps.py` builds the `require_capability` dependency around
`is_capability_allowed`, so the matrix itself stays trivially unit-testable
and the generated role x endpoint matrix test (AC3) can import it directly
to compute each route's expected allow/deny outcome.
"""

from __future__ import annotations

from typing import Final

from collectai.types.enums import Persona

PUBLIC_CAPABILITY: Final[str] = "public"

_ALL_PERSONAS: Final[frozenset[Persona]] = frozenset(Persona)
_OFFICER_ONLY: Final[frozenset[Persona]] = frozenset({Persona.COLLECTIONS_OFFICER})
_CUSTOMER_ONLY: Final[frozenset[Persona]] = frozenset({Persona.CUSTOMER})

# api-contracts.md 1.7. COLLECTIONS_MANAGER holds only `kpi:read` and
# `session:read` (both non-mutating), so AC4's "403 on every mutating
# endpoint" and AC5's "COMPLIANCE_RISK holds no other mutating capability"
# fall directly out of this table rather than needing a separate check.
CAPABILITY_MATRIX: Final[dict[str, frozenset[Persona]]] = {
    "audit:read": frozenset({Persona.COMPLIANCE_RISK}),
    "chat:use": _CUSTOMER_ONLY,
    "compliance:decide": frozenset({Persona.COMPLIANCE_RISK}),
    "conversation:read": _OFFICER_ONLY,
    "customer360:read": _OFFICER_ONLY,
    "demo_controls:use": _OFFICER_ONLY,
    "dispute:read": _OFFICER_ONLY,
    "dispute:resolve": _OFFICER_ONLY,
    "escalation:read": frozenset({Persona.COLLECTIONS_OFFICER, Persona.COMPLIANCE_RISK}),
    "escalation:review": _OFFICER_ONLY,
    "hardship:read": _OFFICER_ONLY,
    "kpi:read": frozenset({Persona.COLLECTIONS_MANAGER}),
    "portfolio:read": _OFFICER_ONLY,
    "ptp:read": _OFFICER_ONLY,
    "ptp:record": _OFFICER_ONLY,
    "recommendation:decide": _OFFICER_ONLY,
    "recommendation:generate": _OFFICER_ONLY,
    "recommendation:read": _OFFICER_ONLY,
    "self:read": _CUSTOMER_ONLY,
    "self:write": _CUSTOMER_ONLY,
    "session:read": _ALL_PERSONAS,
    "snapshot:refresh": _OFFICER_ONLY,
}


class UnknownCapabilityError(KeyError):
    """A route declared a capability absent from `CAPABILITY_MATRIX` (and it
    is not `PUBLIC_CAPABILITY`). A configuration bug in the route
    definition, never a client-triggerable error."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"Unknown capability {capability!r}: add it to CAPABILITY_MATRIX.")


def is_capability_allowed(capability: str, persona: Persona) -> bool:
    """Whether `persona` may use `capability`. `PUBLIC_CAPABILITY` is always
    allowed -- routes using it never resolve a persona at all."""
    if capability == PUBLIC_CAPABILITY:
        return True
    try:
        allowed = CAPABILITY_MATRIX[capability]
    except KeyError as exc:
        raise UnknownCapabilityError(capability) from exc
    return persona in allowed


def capabilities_for_persona(persona: Persona) -> list[str]:
    """Every capability `persona` holds, sorted for a stable response
    (`SessionInfo.capabilities`, api-contracts.md)."""
    return sorted(
        capability for capability, allowed in CAPABILITY_MATRIX.items() if persona in allowed
    )


class UnauthenticatedError(Exception):
    """`X-Persona` is missing/invalid, or a CUSTOMER's `X-Demo-Session` is
    missing, unknown or bound to a different persona (api-contracts.md 1.2).
    Mapped to 401 `UNAUTHENTICATED` by `middleware/errors.py`."""

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ForbiddenError(Exception):
    """`persona` is authenticated but not allowed to use `capability`
    (AC1). Mapped to 403 `FORBIDDEN` by `middleware/errors.py`. The caller
    that raises this (see `api/deps.py`'s `require_capability`) is
    responsible for writing the AC2 `ACCESS_DENIED` audit event first --
    this exception only carries what the error envelope needs to render."""

    def __init__(self, *, capability: str, persona: Persona) -> None:
        self.capability = capability
        self.persona = persona
        super().__init__(
            f"Persona {persona.value} is not allowed to use capability {capability!r}."
        )
