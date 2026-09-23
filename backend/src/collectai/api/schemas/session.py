"""Wire models for the session endpoints (api-contracts.md 3.2: `PersonaOption`,
`DemoCustomer`, `SessionOptionsResponse`, `SessionCreateRequest`, `SessionInfo`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from collectai.types.enums import Persona

_PERSONA_DISPLAY: dict[Persona, tuple[str, str]] = {
    Persona.CUSTOMER: ("Customer", "A customer viewing and managing their own account."),
    Persona.COLLECTIONS_OFFICER: (
        "Collections Officer",
        "Works the delinquent portfolio and individual customer accounts.",
    ),
    Persona.COLLECTIONS_MANAGER: (
        "Collections Manager",
        "Views collections and AI performance KPIs.",
    ),
    Persona.COMPLIANCE_RISK: (
        "Compliance / Risk",
        "Reviews AI-assisted decisions and records compliance decisions.",
    ),
}

DEMO_LABEL = "Demo persona - not real authentication"


class PersonaOption(BaseModel):
    """A persona offered by the switcher."""

    model_config = ConfigDict(frozen=True)

    persona: Persona
    display_name: str
    description: str
    requires_customer_binding: bool


class DemoCustomer(BaseModel):
    """A seeded synthetic customer selectable for the CUSTOMER persona."""

    model_config = ConfigDict(frozen=True)

    customer_id: str
    display_name: str
    account_count: int


class SessionOptionsResponse(BaseModel):
    """Switcher content (`GET /api/session/options`)."""

    model_config = ConfigDict(frozen=True)

    personas: list[PersonaOption]
    demo_customers: list[DemoCustomer]


class SessionCreateRequest(BaseModel):
    """Select a persona (demo, not authentication). Unknown fields are
    rejected (api-contracts.md 1.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona: Persona
    customer_id: str | None = None


class SessionInfo(BaseModel):
    """Current persona session (`POST /api/session`, `GET /api/session/me`)."""

    model_config = ConfigDict(frozen=True)

    persona: Persona
    customer_id: str | None
    display_name: str
    capabilities: list[str]
    demo_label: str = DEMO_LABEL
    session_token: str | None = None
    issued_at: str


def persona_options() -> list[PersonaOption]:
    """Exactly the four personas, in a stable order (api-contracts.md
    `SessionOptionsResponse.personas`: "Exactly the four personas")."""
    return [
        PersonaOption(
            persona=persona,
            display_name=display_name,
            description=description,
            requires_customer_binding=persona is Persona.CUSTOMER,
        )
        for persona, (display_name, description) in _PERSONA_DISPLAY.items()
    ]


def display_name_for(persona: Persona) -> str:
    return _PERSONA_DISPLAY[persona][0]
