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

## Demo controls (demo only)

The demo journeys need the **demo controls**. They are **off by default**, are for demos and development only, and must never be enabled in a real deployment: they change shared demo state (the simulated clock, payments and the seed data).

1. **Turn them on for the API** with `DEMO_CONTROLS_ENABLED=true` (in `.env`, or start with `docker compose -f docker-compose.yml -f docker-compose.test.yml up --build`, which also forces `LLM_MODE=MOCK`). With the flag off there is no navigation link and the `/demo-controls` page shows no control.
2. **Open the app, choose the Collections Officer persona and open _Demo controls_** in the navigation.
3. **Before running the demo journeys, use _Advance clock_ with _Refresh data snapshots_ ticked** (1 day is enough). The seeded data is dated in the past, so every account reads stale until then and customer confirmations (Promise-to-Pay, payment plans, simulated payments) are refused. Do this once for a fresh database, and again after a reseed, which restores the original dates.

The screen also runs the PTP lifecycle job, records a simulated payment and reseeds the seed data. The clock only moves forward and restarting the API resets it. _Refresh data snapshots_ marks every account's snapshot fresh as of the new time; it does not recalculate days past due.

**Known gap:** the stale-data banner's _Refresh_ button on Customer 360 only re-reads the account. It does not refresh the snapshot: the per-account refresh endpoint in the API design (`POST /api/customers/{account_id}/refresh`) is not implemented. Use _Advance clock_ as above.

### Running without Docker (Windows PowerShell)

Docker is not required. This uses the embedded PostgreSQL that the test suite already uses (a temporary database, deleted when you stop it) and needs the backend virtual environment and `npm install` from the sections below. Use three windows from the repository root and keep them open.

```powershell
# Window 1 - temporary database. Copy the DATABASE_URL it prints. Ctrl+C stops it and deletes its data.
cd backend
@'
import tempfile, time
import embedded_postgres as ep
pgdata = tempfile.mkdtemp(prefix="collectai_pg_")
server = ep.get_server(pgdata, cleanup_mode="delete")
print("DATABASE_URL:", server.get_uri())
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    server.cleanup()
'@ | .\.venv\Scripts\python.exe -

# Window 2 - backend on http://localhost:8000 (MOCK mode, demo controls on)
cd backend
$env:DATABASE_URL = "<the URL from window 1>"
$env:LLM_MODE = "MOCK"
$env:DEMO_CONTROLS_ENABLED = "true"
.\.venv\Scripts\python.exe -m collectai.bootstrap.cli migrate
.\.venv\Scripts\python.exe -m collectai.bootstrap.cli seed
.\.venv\Scripts\uvicorn.exe collectai.bootstrap.main:build_app --factory --host 127.0.0.1 --port 8000

# Window 3 - the app on http://localhost:5173 (proxies /api to port 8000)
cd frontend
npm run dev
```

Then follow the demo-controls steps above. In this setup `GET /api/ready` reports `not_ready` because the `collectai_app` database role only exists in the Docker setup; use `GET /api/health` to check the backend is up. Stop with Ctrl+C in windows 3, 2 and 1, in that order.

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

**Reproducible dependencies.** CI and the backend Docker image install with `-c constraints.txt` (`pip install -c constraints.txt -e ".[dev]"`), which pins every backend dependency to an exact version so a new upstream release cannot change the build overnight. The file is resolved for Python 3.11 on Linux, so it is optional for a local virtualenv on another Python or OS and may not install cleanly there. To move to newer dependencies deliberately, run `python scripts/generate_constraints.py` (needs network, installs nothing) and review the diff; `tests/unit/config/test_dependency_constraints.py` checks the file against `pyproject.toml`.

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

CollectAI **targets WCAG 2.1 Level AA**. It does **not** claim conformance. Automated axe, keyboard and focus tests run in CI (`frontend/e2e/accessibility/`), and the manual review of the primary journeys is complete as a checklist, including a human run with Windows Narrator in Microsoft Edge. Five MODERATE and MINOR findings are still open and only that one screen-reader and browser pairing was used, so no conformance is claimed. Results, findings and the rules for when a conformance statement may be made are in [`docs/portfolio/accessibility-review.md`](docs/portfolio/accessibility-review.md).

## Repository layout

See `specs/design/folder-structure.md` for the full target layout and `specs/design/component-map.md` for which story owns which file.
