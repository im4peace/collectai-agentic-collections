# CollectAI — Claude Code Instructions

## Product

CollectAI is an AI-native Collections & Recovery platform for banks.

This repository is a portfolio and learning project demonstrating:
- AI Product Management
- Agentic AI architecture
- Full-stack engineering
- Claude Code workflows
- Human-in-the-loop AI
- Deterministic financial decisioning
- AI evaluation and governance

## Source of Truth

Before designing or implementing functionality, read:

1. `docs/PRODUCT_VISION.md`
2. `docs/MVP_REQUIREMENTS.md`

Product requirements take precedence over implementation assumptions.

## Core Engineering Principle

LLMs understand, classify, summarize, recommend and explain.

Deterministic services calculate, validate eligibility, modify financial state and execute financial actions.

Never delegate financial calculations or binding financial decisions to an LLM.

## Safety

This is a demonstration application.

Use synthetic data only.

Never introduce:
- Real customer PII
- Real bank credentials
- Production banking integrations
- Real account credentials
- Card numbers
- CVVs
- PINs
- Government identifiers

## Human-in-the-Loop

Sensitive actions must remain under human control, including:

- Settlements
- Restructuring
- Exceptional payment arrangements
- Policy exceptions
- Vulnerable-customer scenarios
- High-risk compliance cases

## Architecture Expectations

Maintain clear separation between:

- UI
- API
- Domain services
- Deterministic rules engine
- AI orchestration
- Data persistence
- Audit
- Evaluation

Avoid unnecessary complexity.

## AI Requirements

AI functionality should prefer:

- Structured outputs
- Explicit tool contracts
- Deterministic validation
- Guardrails
- Traceability
- Human escalation
- Evaluation datasets

Do not trust free-form LLM output for business-critical actions.

## Development Workflow

For significant features:

Requirements
→ Architecture
→ Implementation Plan
→ Tests
→ Implementation
→ Validation
→ Review

Do not start implementation when requirements are materially ambiguous.

## Testing

Test:

- Business rules
- API behavior
- Authorization
- Financial calculations
- State transitions
- AI structured outputs
- Guardrails
- Human escalation
- Failure scenarios

## Git

Use feature branches.

Examples:

`feat/collections-portfolio`
`feat/customer-360`
`feat/ai-strategy-agent`

Use conventional commits:

`feat:`
`fix:`
`test:`
`docs:`
`refactor:`
`chore:`

Do not commit secrets or environment files.
