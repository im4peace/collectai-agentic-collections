"""Unit tests for the pure capability matrix (E3-S1 AC1, AC4, AC5). No I/O:
these exercise `api/rbac.py` directly, independent of the HTTP-level
matrix test in `bt/api/test_e3_s1_rbac_matrix.py`."""

from __future__ import annotations

import pytest

from collectai.api.rbac import (
    CAPABILITY_MATRIX,
    PUBLIC_CAPABILITY,
    UnknownCapabilityError,
    capabilities_for_persona,
    is_capability_allowed,
)
from collectai.types.enums import Persona

_COMPLIANCE_RISK_MUTATING_CAPABILITY = "compliance:decide"


def test_public_capability_is_allowed_for_every_persona() -> None:
    for persona in Persona:
        assert is_capability_allowed(PUBLIC_CAPABILITY, persona) is True


def test_unknown_capability_raises_a_named_error() -> None:
    with pytest.raises(UnknownCapabilityError, match="not-a-real-capability"):
        is_capability_allowed("not-a-real-capability", Persona.COLLECTIONS_OFFICER)


def test_session_read_is_allowed_for_every_persona() -> None:
    for persona in Persona:
        assert is_capability_allowed("session:read", persona) is True


@pytest.mark.parametrize(
    "capability",
    sorted(capability for capability in CAPABILITY_MATRIX if capability != "session:read"),
)
def test_collections_manager_holds_only_session_read_and_kpi_read(capability: str) -> None:
    """AC4: COLLECTIONS_MANAGER receives 403 on every mutating endpoint --
    at the matrix level, that means it holds no capability besides the two
    read-only ones the switcher/dashboard need."""
    if capability == "kpi:read":
        assert is_capability_allowed(capability, Persona.COLLECTIONS_MANAGER) is True
    else:
        assert is_capability_allowed(capability, Persona.COLLECTIONS_MANAGER) is False


@pytest.mark.parametrize(
    "capability",
    sorted(capability for capability in CAPABILITY_MATRIX if capability != "session:read"),
)
def test_compliance_risk_holds_no_mutating_capability_except_compliance_decide(
    capability: str,
) -> None:
    """AC5."""
    expected = capability in {"audit:read", "escalation:read", _COMPLIANCE_RISK_MUTATING_CAPABILITY}
    assert is_capability_allowed(capability, Persona.COMPLIANCE_RISK) is expected


def test_compliance_risk_is_forbidden_for_every_other_mutating_capability() -> None:
    """AC5, phrased directly: `compliance:decide` is the only mutating
    capability COMPLIANCE_RISK ever holds."""
    mutating_capabilities = {
        "chat:use",
        "demo_controls:use",
        "dispute:resolve",
        "escalation:review",
        "ptp:record",
        "recommendation:decide",
        "recommendation:generate",
        "self:write",
    }
    for capability in mutating_capabilities:
        assert is_capability_allowed(capability, Persona.COMPLIANCE_RISK) is False
    assert is_capability_allowed(_COMPLIANCE_RISK_MUTATING_CAPABILITY, Persona.COMPLIANCE_RISK)


def test_capabilities_for_persona_matches_the_matrix_for_every_persona() -> None:
    for persona in Persona:
        expected = sorted(
            capability for capability, allowed in CAPABILITY_MATRIX.items() if persona in allowed
        )
        assert capabilities_for_persona(persona) == expected
