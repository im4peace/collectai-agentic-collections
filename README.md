# CollectAI

AI-native Collections & Recovery platform for banks (portfolio and learning project). See `docs/PRODUCT_VISION.md` and `docs/MVP_REQUIREMENTS.md` for product scope, and `CLAUDE.md` for engineering principles.

**Synthetic data only.** No real customer PII, credentials, card numbers, CVVs, PINs or government identifiers ever appear in this repository, its seed data, or its logs.

## Scope decision: local Docker Compose only

This project targets **local Docker Compose and CI**. There is no production deployment configuration, no cloud infrastructure and no Terraform/Pulumi — `docker-compose.yml`, `docker-compose.test.yml`, the two Dockerfiles, `deploy/`, and `.github/workflows/ci.yml` are the entire deployment surface. See `specs/design/deployment.md` for the full design rationale, including what a hosted demo *would* need if one were ever built (it is not built here).

## Quick start (clean checkout)

```bash
cp .env.example .env
docker compose up --build
```

This starts four services: `db` (PostgreSQL 16), `migrate` (applies migrations, then loads synthetic seed data, then exits), `api` (FastAPI on port 8000), and `web` (the SPA on port 8080, nginx-served, proxying `/api` to `api`).

Once `migrate` finishes, check readiness:

```bash
curl http://localhost:8000/api/ready
```

Reports `{"status": "ready", ...}` once the database is migrated, exactly one PolicyRuleSet version is active, and the `audit_event` table's role grants are intact. The app is at `http://localhost:8080`.

Reset everything (drops the database volume): `docker compose down -v`.

## Applying migrations and seed data manually

The `migrate` service does this automatically on `docker compose up`, but it can also be run on demand against a running `db`:

```bash
make migrate   # alembic upgrade head, as the collectai_owner role
make seed      # generate, validate, scan and idempotently load synthetic seed data
```

`make seed` refuses to load any dataset that fails validation or the prohibited-pattern scan (`backend/src/collectai/persistence/seed/scanner.py`) — it never loads real-looking PII.

## Running tests (MOCK only, no network)

```bash
make test           # backend (unit + real-PostgreSQL) + frontend
make test-backend
make test-frontend
```

`LLM_MODE` defaults to `MOCK` (`backend/src/collectai/config/settings.py`), and the full backend and frontend suites run with **no `ANTHROPIC_API_KEY` set and no network call to the provider** (E1-S5 AC3): `backend/src/collectai/llm_provider/mock.py` is a scriptable, deterministic in-process provider, and `tests/db/conftest.py` starts its own embedded PostgreSQL instance rather than requiring a running database. Backend tests are split by pytest marker: `unit` (no I/O) and `db` (real PostgreSQL, via `embedded-postgres`, started automatically).

## Linting and architecture checks

```bash
make lint   # ruff + mypy (backend), eslint + tsc (frontend)
make arch   # import-linter contracts + tests/architecture
```

## Local (non-Docker) backend development

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip on macOS/Linux
.venv/Scripts/python -m pytest
```

Point `DATABASE_URL` at a local PostgreSQL instance (or run `docker compose up db` and connect to `localhost:5432`) and run the API with `uvicorn collectai.bootstrap.main:build_app --factory --reload`.

## Local (non-Docker) frontend development

```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api to :8000
npm run test:run
```

## CI

`.github/workflows/ci.yml` runs on every push and pull request: `lint-type`, `backend-unit`, `backend-db`, `architecture`, `frontend`. No repository secret is configured and `ANTHROPIC_API_KEY` is never set in the workflow, so LIVE mode never runs in CI. See that file's header comment for which additional jobs later stories add (data safety scans, MOCK evaluation, OpenAPI contract drift, end-to-end journeys).

## Accessibility

CollectAI **targets WCAG 2.1 Level AA**. It does **not** claim conformance. Automated axe, keyboard and focus tests run in CI (`frontend/e2e/accessibility/`), and a manual review of the primary journeys has been started but is not complete: it still has open findings and has not yet been run with a real screen reader. Results, findings and the rules for when a conformance statement may be made are in [`docs/portfolio/accessibility-review.md`](docs/portfolio/accessibility-review.md).

## Repository layout

See `specs/design/folder-structure.md` for the full target layout and `specs/design/component-map.md` for which story owns which file.
