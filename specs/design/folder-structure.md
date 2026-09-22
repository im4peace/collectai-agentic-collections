# CollectAI Folder Structure

Target repository layout after implementation. Today only `docs/`, `specs/`, `CLAUDE.md` and `.claude/` exist; every other path is created by the stories listed in `component-map.md`. Import rules are the one-way layering defined in `system-design.md` section 3 and enforced by `backend/.importlinter` plus `backend/tests/architecture/`.

Path shorthand used in `component-map.md`: `be/` = `backend/src/collectai/`, `bt/` = `backend/tests/`, `ev/` = `backend/collectai_eval/`, `fe/` = `frontend/src/`, `e2e/` = `frontend/e2e/`.

## 1. Top level

```
collectai-agentic-collections/
├── CLAUDE.md                          # Project instructions (exists)
├── README.md                          # Local start, commands, MOCK/LIVE, "targets WCAG 2.1 AA" statement
├── Makefile                           # up, down, migrate, seed, test, e2e, eval-mock, eval-live, lint, arch
├── docker-compose.yml                 # db, migrate, api, web (MOCK by default)
├── docker-compose.test.yml            # Override for CI and e2e: MOCK, DEMO_CONTROLS_ENABLED=true, seeded db
├── .env.example                       # Placeholder variables only
├── .gitignore                         # .env, caches, build output, coverage, playwright reports
├── .github/workflows/ci.yml           # Push CI: lint, unit, db, api, architecture, data-safety, eval-mock, frontend, e2e
├── backend/                           # Python API, domain, rules, AI orchestration, persistence, evaluation
├── frontend/                          # React + Vite + TypeScript SPA and Playwright tests
├── deploy/                            # Local container support files (nginx config, db init SQL)
├── scripts/                           # Repo-level helper scripts (contract generation, scans)
├── docs/                              # Product docs (exist) and portfolio deliverables
└── specs/                             # Requirements and design (exist)
```

## 2. Backend

```
backend/
├── pyproject.toml                     # Dependencies, ruff, mypy (strict for types/rules_engine), pytest markers
├── alembic.ini                        # Alembic config (script_location = src/collectai/persistence/migrations)
├── Dockerfile                         # Multi-stage image for api and migrate/seed jobs
├── .importlinter                      # import-linter contracts: layers, forbidden imports, independence
├── src/collectai/                     # Production package ("be/")
│   ├── types/                         # Layer 0: Money, Clock, ids, enums, domain models, reason codes, RuleResult
│   │   ├── money.py                   #   Decimal Money, NEGATIVE_AMOUNT / OVER_PRECISION, string serialization
│   │   ├── clock.py                   #   Clock protocol, SystemClock, SimulatedClock
│   │   ├── enums.py                   #   All enums mirrored from api-contracts.md section 5
│   │   ├── ids.py                     #   Prefixed id generation and validation
│   │   ├── reason_codes.py            #   Stable reason-code catalogue
│   │   ├── results.py                 #   RuleResult, PolicyUnavailable, failure types
│   │   └── models/                    #   Pydantic domain models (account, delinquency, ptp, payment, arrangement, escalation, ...)
│   ├── config/                        # Layer 1: validated settings and versioned PolicyRuleSet
│   │   ├── settings.py                #   Environment settings, named startup errors
│   │   └── policy/                    #   models.py, validator.py (contract + cross-field rules), loader.py, provider.py, policy-v1.json
│   ├── persistence/                   # Layer 2: PostgreSQL access
│   │   ├── db.py                      #   Engine, session factory, UnitOfWork
│   │   ├── orm/                       #   SQLAlchemy 2.0 table models (one module per entity group)
│   │   ├── repositories/              #   Customer-scoped and staff repositories, idempotency store
│   │   ├── migrations/                #   Alembic env.py and versions/ (NUMERIC money, partial unique indexes, grants, triggers)
│   │   └── seed/                      #   generator.py, validator.py, scanner.py (prohibited patterns), cli entry
│   ├── audit/                         # Layer 3: append-only audit
│   │   ├── service.py                 #   record_in (same transaction) and record (raises AuditUnavailable)
│   │   ├── redaction.py               #   Secret and identifier redaction
│   │   ├── events.py                  #   Event type catalogue and builders
│   │   └── queries.py                 #   Chain and filter queries for the audit API
│   ├── rules_engine/                  # Layer 4a: deterministic, pure, no I/O, no AI imports
│   │   ├── priority.py                #   Score, band, factors, human_treatment flags
│   │   ├── ptp_rules.py               #   PTP amount and date validation, alternatives, satisfaction rule
│   │   ├── payable.py                 #   PAY_NOW payable amounts
│   │   ├── arrangement.py             #   Eligible options, exact-sum schedules, exception classification and authority
│   │   ├── contact_policy.py          #   MAX_ATTEMPTS, MIN_INTERVAL
│   │   ├── suppression.py             #   Item and account scope suppression
│   │   ├── freshness.py               #   FRESH, STALE, UNKNOWN
│   │   ├── consistency.py             #   INCONSISTENT_RECORD checks
│   │   └── routing.py                 #   Reason to queue, reviewer role, priority
│   ├── llm_provider/                  # Layer 4b: the only package that imports the anthropic SDK
│   │   ├── base.py                    #   LlmProvider protocol, ProviderResult, ProviderTimeout
│   │   ├── mock.py                    #   Scriptable MockProvider (no network)
│   │   ├── anthropic_live.py          #   AnthropicProvider (LIVE)
│   │   └── factory.py                 #   Selects provider from LLM_MODE
│   ├── domain_services/               # Layer 5a: state transitions; revalidate, transition, audit, idempotency
│   │   ├── ptp_service.py             #   Create, cancel PTP (manual and confirmed paths)
│   │   ├── payment_service.py         #   Simulated payment recording (no HTTP client)
│   │   ├── ptp_lifecycle.py           #   KEPT / BROKEN transitions, rerunnable
│   │   ├── arrangement_service.py     #   Create arrangement from eligible option or approved exception
│   │   ├── escalation_service.py      #   Case creation via routing, suppression, idempotent
│   │   ├── review_service.py          #   Reviewer actions, state machine, optimistic version
│   │   ├── exception_handling.py      #   Exceptional-arrangement approval within policy authority (Slice 2)
│   │   ├── compliance_service.py      #   record_compliance_review_decision (narrow capability)
│   │   ├── hardship_service.py        #   HardshipCase creation and decision support
│   │   ├── dispute_service.py         #   Dispute creation, review, resolution
│   │   ├── proposal_service.py        #   Proposal creation, expiry, invalidation
│   │   ├── snapshot_service.py        #   Simulated core sync and freshness gate
│   │   ├── portfolio_service.py       #   Portfolio read model with priority
│   │   ├── customer360_service.py     #   Customer 360 read model
│   │   ├── kpi_service.py             #   KPI aggregation (Decimal)
│   │   ├── demo_controls_service.py   #   Clock advance, reseed, simulated payment trigger
│   │   └── idempotency.py             #   Idempotency helper used by all services
│   ├── ai_orchestration/              # Layer 5b: imports only types, config, audit, llm_provider
│   │   ├── ports.py                   #   Protocols the application layer implements (no service imports)
│   │   ├── orchestrator.py            #   Provider call, retry, safe fallback, latency capture
│   │   ├── structured_output.py       #   Schema validation and bounded retry
│   │   ├── schemas/                   #   IntentResult, NextBestAction, tool argument models
│   │   ├── prompts/                   #   builder.py (allow-list) and versioned templates intent_v1.py, nba_v1.py, arrangement_v1.py
│   │   ├── safety_precedence.py       #   Deterministic sensitive-over-transactional rule
│   │   ├── grounding.py               #   Figure, date and option extraction and comparison
│   │   ├── templates.py               #   Customer-facing templates built from service output
│   │   └── tools/                     #   registry.py (six tools), read_tools.py, propose_tools.py, cap and idempotency
│   ├── application/                   # Layer 6: use-case orchestration across AI and domain services
│   │   ├── chat_flow.py               #   Turn processing (classify, precedence, tools, grounding, persist, audit)
│   │   ├── confirmation_flow.py       #   Explicit confirm and cancel of proposals
│   │   ├── recommendation_flow.py     #   Next-best-action generation and officer decision
│   │   └── tool_backend.py            #   Implements ai_orchestration.ports using domain_services and rules_engine
│   ├── api/                           # Layer 7: HTTP
│   │   ├── app.py                     #   FastAPI factory, middleware order, exception handlers
│   │   ├── rbac.py                    #   Capability matrix and require_capability dependency
│   │   ├── deps.py                    #   Persona and bound-customer resolution, unit of work, clock, settings
│   │   ├── middleware/                #   correlation.py, errors.py, rate_limit.py, demo_gate.py, idempotency.py
│   │   ├── schemas/                   #   Pydantic wire models matching api-contracts.schema.json
│   │   └── routers/                   #   system, session, portfolio, customer360, recommendations, ptps, me, chat, escalations, hardship, disputes, audit, kpis, demo_controls
│   ├── jobs/                          # Layer 7: scheduler (APScheduler) invoking ptp_lifecycle
│   │   └── scheduler.py
│   ├── bootstrap/                     # Layer 8: composition root, only place that wires implementations
│   │   ├── container.py               #   Builds provider, services, ports adapters
│   │   ├── main.py                    #   ASGI entry (app), startup validation
│   │   └── cli.py                     #   python -m collectai.bootstrap.cli: migrate, seed, policy activate
│   └── py.typed
├── collectai_eval/                    # Evaluation package ("ev/"): imports production code, imported by none
│   ├── datasets/                      #   eval-ds-v1.json (version, provenance, labelled cases), safety set
│   ├── runner.py                      #   MOCK and LIVE runner, refuses LIVE in CI
│   ├── metrics.py                     #   Accuracy, per-category recall, escalation metrics, safety set
│   ├── report.py                      #   30-case rule, separate MOCK and LIVE sections
│   ├── store.py                       #   Writes eval_run and eval_case_result
│   └── cli.py                         #   python -m collectai_eval
├── scripts/                           # generate_openapi.py, generate_portfolio_docs.py, scan_prohibited_patterns.py
└── tests/                             # Test suites ("bt/")
    ├── conftest.py                    #   Fixtures: TestClock, MockProvider, db, personas, socket blocker
    ├── unit/                          #   Pure unit tests per package (types, config, rules_engine, audit, ai_orchestration, domain_services)
    ├── db/                            #   Repository, migration, grant and constraint tests (real PostgreSQL)
    ├── api/                           #   Endpoint, RBAC matrix, ownership matrix, contract, idempotency tests
    ├── architecture/                  #   Import-boundary and no-payment-gateway tests
    ├── ai_guardrails/                 #   Hostile provider, grounding, safety precedence, tool cap, template tests
    ├── redteam/                       #   Prompt-injection and critical-violation suites
    ├── security/                      #   Prohibited-pattern, log and prompt leakage scans
    ├── evaluation/                    #   Evaluation framework and metrics tests
    ├── journeys/                      #   API-level journey assertions used by e2e
    └── fixtures/                      #   Synthetic fixtures (accounts, policy variants, hostile outputs)
```

## 3. Frontend

```
frontend/
├── package.json                       # Scripts: dev, build, test (Vitest), e2e (Playwright), lint, gen:api
├── vite.config.ts                     # Vite config, /api dev proxy
├── tailwind.config.ts                 # Design tokens (neutral banking theme, status colors with text labels)
├── tsconfig.json                      # Strict TypeScript
├── eslint.config.js                   # jsx-a11y, no-restricted-imports (features do not import each other)
├── Dockerfile                         # Build then nginx runtime
├── src/                               # Application ("fe/")
│   ├── main.tsx                       #   Entry
│   ├── app/                           #   Providers, router, layouts (CustomerLayout, InternalLayout), route guards, forbidden page
│   ├── api/                           #   Typed client, generated types (gen:api), persona and session headers, error envelope handling
│   ├── auth/                          #   Persona switcher state, demo session, capability helpers, demo label
│   ├── components/                    #   Shared UI: Badge (text plus icon), MoneyText, DataTable, ConfirmDialog, LiveRegion, SourcePanel (AI-generated, Rules engine)
│   ├── features/
│   │   ├── session/                   #   Persona switcher and demo customer picker
│   │   ├── portfolio/                 #   Portfolio screen: filters, sort, URL state
│   │   ├── customer360/               #   Customer 360 screen, record PTP form, stale banner, AI unavailable state
│   │   ├── chat/                      #   Customer chat, proposal Confirm/Cancel, Talk to a human, simulated labels
│   │   ├── escalations/               #   Minimal list (Slice 1), review queue and case detail (Slice 2)
│   │   ├── audit/                     #   Audit trail viewer timeline
│   │   ├── dashboard/                 #   KPI dashboard (Slice 4)
│   │   └── demo-controls/             #   Flag-gated panel
│   ├── lib/                           #   Formatting, focus management, aria helpers, query keys
│   └── test/                          #   Vitest setup, MSW handlers, axe helper
├── e2e/                               # Playwright ("e2e/")
│   ├── fixtures/                      #   Persona login helpers, seeded data, clock control, axe fixture
│   ├── journeys/                      #   journey-a-ptp, journey-b1-arrangement, journey-b2-hardship, journey-c-dispute
│   ├── accessibility/                 #   axe scans, keyboard, focus, live region, non-color-only checks
│   └── perf/                          #   Page-load harness (30 loads after warm-up)
└── public/
```

## 4. Deploy, scripts, docs

```
deploy/
├── nginx/default.conf                 # Serves the SPA, proxies /api to api:8000, security headers
└── db/init-roles.sql                  # Creates collectai_owner, collectai_app, collectai_readonly roles and grants

scripts/
├── gen_openapi_types.sh               # Regenerate frontend types from api-contracts.schema.json
└── check_contract_drift.sh            # Compare FastAPI OpenAPI against api-contracts.schema.json

docs/
├── PRODUCT_VISION.md                  # Source of truth (exists)
├── MVP_REQUIREMENTS.md                # Source of truth (exists)
└── portfolio/
    ├── kpi-tree.md                    # P1
    ├── ai-evaluation-report.md        # P2 (generated: MOCK and LIVE separate)
    ├── ai-risk-register.md            # P3 (27 failure scenarios, 9 top risks)
    ├── decision-log.md                # P4 (seeded from BRD section 16)
    └── accessibility-review.md        # Manual accessibility review results

specs/
├── brd/brd.md                         # Approved BRD (exists)
├── stories/                           # 54 story files and dependency-graph.md (exist)
├── policy-ruleset-contract.md         # PolicyRuleSet contract (exists)
├── features.json                      # Feature list (exists)
└── design/                            # api-contracts, data-models, system-design, folder-structure, component-map, deployment, mockups
```

## 5. Import rules at a glance

Lower rows may not import higher rows. Same-row packages may not import each other. Enforced by `.importlinter` (layers and forbidden contracts) and `backend/tests/architecture/`.

| Order | Package | Allowed imports | Explicitly forbidden |
|---|---|---|---|
| 0 | `types` | stdlib, pydantic | all `collectai` packages |
| 1 | `config` | `types` | layers 2 and up |
| 2 | `persistence` | `types`, `config` | `audit`, `rules_engine`, AI, API |
| 3 | `audit` | `types`, `config`, `persistence` | rules, AI, API |
| 4 | `rules_engine`, `llm_provider` (siblings) | `types`, `config` (`llm_provider` also `anthropic`) | `rules_engine` importing `llm_provider`, `ai_orchestration`, `persistence`, network; `llm_provider` importing `rules_engine`, `domain_services` |
| 5 | `domain_services`, `ai_orchestration` (siblings) | domain: layers 0 to 4 (rules, audit, persistence); AI: `types`, `config`, `audit`, `llm_provider` | domain importing `ai_orchestration`, `llm_provider`, `anthropic`; AI importing `rules_engine`, `domain_services`, `persistence` |
| 6 | `application` | layers 0 to 5 | `api`, `bootstrap` |
| 7 | `api`, `jobs` | `application`, `domain_services`, `audit`, `types`, `config` | `llm_provider`, `ai_orchestration`, `bootstrap` (AI only through `application`) |
| 8 | `bootstrap` | all of the above | none |
| off-tree | `collectai_eval` | any `collectai` package | imported by any production package |
| frontend | `features/*` | `components`, `api`, `auth`, `lib` | another `features/*` module |
