# CollectAI Deployment, CI/CD and Operations

Scope decision: CollectAI is a portfolio demo with synthetic data. E1-S5 AC5 requires that **no production deployment configuration is included: only local Compose files and the CI workflow exist**. This document therefore designs a **local-Docker-Compose-first** setup plus CI, and records what a hosted environment would need as a *future consideration* without creating any of those files.

## 1. Environments

| Environment | Purpose | How it runs | Data | LLM mode |
|---|---|---|---|---|
| **local** (primary) | Development, demo, screenshots | `docker compose up` (db, migrate+seed, api, web) | Synthetic seed (500 accounts default, 200 to 1,000 allowed, 1,000 for perf) | MOCK default; LIVE only when the developer sets `LLM_MODE=LIVE`, `ANTHROPIC_MODEL`, `ANTHROPIC_API_KEY` in a git-ignored `.env` |
| **ci** | Automated verification on every push | GitHub Actions runners with a PostgreSQL service container and the same Compose file for E2E | Synthetic seed | MOCK only. No API key is configured in CI, and the LIVE runner refuses when `CI` is set |
| staging | Not built (E1-S5 AC5); reference design only | Same images on one VM or container service, managed PostgreSQL, `DEMO_CONTROLS_ENABLED=true`, MOCK | Synthetic seed | MOCK |
| prod | Not built and not appropriate for a demonstration application; reference design only | Same images behind TLS and an identity-aware proxy (the persona header is not authentication), `DEMO_CONTROLS_ENABLED=false`, secrets from the host secret store | Synthetic seed only | MOCK by default |

Future (not built): a single-VM hosted demo could reuse the same images with an external managed PostgreSQL, TLS termination in front of nginx, `DEMO_CONTROLS_ENABLED=false`, and secrets from the host's secret store. Kubernetes and multi-instance deployment would first need a shared rate-limit store and a scheduler leader lock (in-process scheduler and limiter assume one API instance).

## 2. Local runtime topology (docker-compose.yml)

| Service | Image / build | Role | Notes |
|---|---|---|---|
| `db` | `postgres:16` | Database | Volume `pgdata`; init script `deploy/db/init-roles.sql` creates `collectai_owner` and `collectai_app`; healthcheck `pg_isready` |
| `migrate` | `backend/Dockerfile` (one-shot) | `python -m collectai.bootstrap migrate` as owner role, then `python -m collectai.bootstrap seed` (idempotent; validation + prohibited-pattern scan), then exits | `depends_on: db (healthy)`; re-runnable |
| `api` | `backend/Dockerfile` | FastAPI via uvicorn, connects as `collectai_app` | `depends_on: migrate (completed)`; healthcheck `GET /api/ready`; env from `.env` |
| `web` | `frontend/Dockerfile` (multi-stage: build, then nginx) | Serves the SPA and proxies `/api` to `api:8000` | Same-origin, so no CORS; security headers set |
| (test override) | `docker-compose.test.yml` | CI and E2E: MOCK, `DEMO_CONTROLS_ENABLED=true`, seeded database | Playwright runs from the host or CI runner against `web` |

Ports: web 8080 (`http://localhost:8080`), api 8000, db 5432 (bound to localhost only). For frontend development `npm run dev` (Vite, port 5173) proxies `/api` to the api container; for backend development run uvicorn with `--reload` against the compose database.

One documented command from a clean checkout (E1-S5 AC1): `cp .env.example .env && docker compose up --build`, after which the API reports ready (`GET /api/ready`) and the app is at `http://localhost:8080`. Documented reset: `docker compose down -v`. `make test` runs the MOCK-only backend and frontend suites without the network and without `ANTHROPIC_API_KEY` (E1-S5 AC3).

### 2.1 Configuration and secrets
- All configuration via environment variables validated at startup (data-models 5.1). `.env` is git-ignored; `.env.example` lists every key with placeholder values only (for example `ANTHROPIC_API_KEY=` empty, `ANTHROPIC_MODEL=` empty, `DATABASE_URL=postgresql+psycopg://collectai_app:change-me@db:5432/collectai`). The DB passwords in Compose are local-only defaults from `.env`, not real credentials.
- No model id, key or password appears in source, images, Compose files or logs. The API key is a `SecretStr`, never echoed by `/api/meta` or logs; the LIVE mode banner shows only the mode name.
- Secrets for CI: none required. The CI workflow declares `permissions: contents: read` and no repository secrets; a fork or pull request therefore cannot reach the paid API, and the workflow has no LIVE job at all.
- A pre-commit hook and the CI `data-safety` job scan for key-like strings and prohibited identifiers; `.env` is checked to be untracked (`git ls-files .env` must be empty).

## 3. CI/CD pipeline (.github/workflows/ci.yml)

Triggers: every push and pull request. All jobs run in MOCK mode and fail the build on any failure. There is **no CD**: the deliverable is the repository plus local Compose; "release" means a tagged commit.

| Job | Steps | Gate |
|---|---|---|
| `lint-type` | ruff, mypy (strict on core, rules_engine, domain), ESLint, `tsc --noEmit` | zero errors |
| `backend-unit` | pytest `backend/tests/unit`, `tests/evaluation` with coverage (rules_engine, domain >= 90 percent) | pass + coverage |
| `backend-db-api` | PostgreSQL 16 service, run migrations as owner, pytest `tests/db`, `tests/api`, `tests/ai_guardrails`, `tests/journeys` connecting as the app role (audit UPDATE/DELETE denied, RBAC and ownership matrices, contract test against `specs/design/api-contracts.schema.json`, hostile-provider fuzz, tool-cap boundary) with sockets blocked for MOCK | pass |
| `architecture` | `lint-imports` (import-linter contracts in `backend/.importlinter`) and AST tests in `tests/architecture` (no `anthropic` outside `llm_provider`, no wall-clock, no gateway SDK, LLM-reachable path scan, nothing imports `evaluation`) | pass |
| `data-safety` | `scripts/scan_prohibited_patterns.py` over seed output, prompt templates, fixtures, captured test logs; `tests/security` and the red-team suite `tests/redteam` (>= 20 cases, one per BRD 4.2 violation type, zero critical violations); a self-test plants a card number and asserts the scan fails | pass |
| `eval-mock` | `python -m collectai_eval run --mode MOCK` on the committed dataset; writes the MOCK section of the report as an artifact; asserts MOCK is never labelled as evidence of quality | pass |
| `frontend` | `npm ci`, Vitest + RTL, `npm run build` | pass |
| `openapi-contract` | `scripts/generate_openapi.py` and `scripts/check_contract_drift.sh`: diff FastAPI's OpenAPI against `specs/design/api-contracts.schema.json`; regenerate TS types and fail on drift | no drift |
| `e2e` | `docker compose -f docker-compose.yml -f docker-compose.test.yml up --build` (MOCK, `DEMO_CONTROLS_ENABLED=true`, seeded) then Playwright: Journey A (Slice 1, later B1, B2, C as delivered), axe scans on every delivered screen, keyboard and focus suites; uploads traces and axe reports; states "targets WCAG 2.1 AA, no conformance claim" in the report | pass |
| `supply-chain` (non-blocking) | `pip-audit`, `npm audit`, lockfile check | reported |

Performance measurement (E3-S3 AC5, E4-S2 AC5, BRD 10.6) is a **manually triggered** script (`frontend/e2e/perf/`, 30 runs after one warm-up, 1,000-account seed, hardware recorded) because CI runners are not representative hardware; its result is committed to `docs/portfolio/`. LIVE evaluation is likewise only run locally: `make eval-live` (requires `--live`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, optional `EVAL_BUDGET_USD`; exits with an error if `CI` is set) and its report is committed manually.

Branching and commits follow `CLAUDE.md`: feature branches (`feat/...`), conventional commits, no secrets or `.env` committed. Slice exit criteria (BRD 7.2) are checked by the corresponding CI jobs plus the manual LIVE baseline and manual accessibility review.

## 4. Infrastructure as code
No cloud infrastructure exists, so no Terraform or Pulumi is introduced (avoiding unnecessary complexity). The **declarative artifacts are**: `docker-compose.yml`, `docker-compose.test.yml`, the two Dockerfiles, `deploy/nginx/default.conf`, `deploy/db/init-roles.sql` (roles and grants as code), Alembic migrations (schema as code, including audit triggers and grants), the versioned policy files (`backend/src/collectai/config/policy/`), and `.github/workflows/ci.yml`. If a hosted demo is added later, the recommended approach is a small Terraform module for one VM or container service and a managed PostgreSQL, with the same images and `init-roles.sql` applied by a migration job.

## 5. Database operations
- **Migrations**: Alembic, applied by the `migrate` service as `collectai_owner`; the running app never holds owner rights. Migrations are forward-only in normal use and follow expand-then-contract for column changes. Downgrades exist for development but the audit table migration is never downgraded destructively.
- **Backups**: not needed for synthetic data; recreation is `docker compose down -v && docker compose up`. If an audit-preserving reset is wanted, `pg_dump -t audit_event` before `down -v` (documented in the README).
- **Reseed**: `python -m collectai.bootstrap seed` (idempotent upsert) or the flag-gated demo reseed endpoint (deletes business tables, keeps `audit_event`, deterministic ids).
- **Readiness contract** (`GET /api/ready`): database reachable, migrations at head, exactly one valid ACTIVE policy version, audit grants intact (INSERT/SELECT only). The API refuses to start if settings or the active policy are invalid, or if the app role can UPDATE or DELETE `audit_event`.

## 6. Rollback and recovery
| Change | Rollback |
|---|---|
| Application code | `git revert` the merge commit (or check out the previous tag) and rebuild images; `docker compose up --build` |
| Schema migration | Restore the previous image plus `alembic downgrade -1` for dev-only revisions; for anything applied to a kept database use a new forward migration (expand/contract). Data-losing migrations are not allowed on `audit_event` |
| PolicyRuleSet | Versions are immutable. Roll back by activating the previous version: `python -m collectai.bootstrap policy-activate policy-v1` (audited as `POLICY_ACTIVATED`). Audit events already reference the version used, so history stays resolvable |
| LLM configuration | Set `LLM_MODE=MOCK` (or unset `ANTHROPIC_MODEL`) and restart; the app runs fully without the provider and the UI shows the AI-unavailable/manual workflow states |
| Corrupted demo data | Demo reseed control or `docker compose down -v` |
| Bad dataset or prompt version | Revert the dataset file in `backend/collectai_eval/datasets/` or the prompt template; versions are recorded on every EvalRun and AI interaction |

## 7. Observability in operation
Structured JSON logs to stdout (collected by `docker compose logs`), correlation id on every line, no request bodies, redaction filter shared with the audit layer. Health: container healthchecks on `db`, `api` (`/api/ready`), `web`. No metrics stack (demo). KPIs and AI telemetry are read from the database via `/api/kpis`.

## 8. Operational runbook (demo)
| Symptom | Likely cause | Action |
|---|---|---|
| API exits at startup naming a parameter | Invalid `.env` value or policy file | Fix the named key or policy parameter (contract ranges in data-models 5 and 5.1) |
| API exits "audit role can mutate" | Grants changed manually | Re-run `deploy/db/init-roles.sql` and the audit-grant migration as owner |
| Chat replies "AI unavailable" | LIVE mode without a valid key/model or provider timeout | Check `/api/meta` `llm_mode`; switch to MOCK; "Talk to a human" still works |
| Every recommendation is HUMAN_REVIEW_ONLY | Account has an open escalation/hardship/dispute | Expected behaviour; decide the case in the review queue |
| 503 POLICY_UNAVAILABLE | No valid ACTIVE policy row | Activate a valid version via the CLI |
| Snapshot banner "stale" | Seed older than `freshness.max_snapshot_age_minutes` or clock advanced | Use Refresh on Customer 360 (or reseed) |
