# CollectAI developer commands (E1-S5). Only targets backed by real,
# existing tooling are listed here -- `e2e`, `eval-mock` and `eval-live` are
# added by the stories that build those subsystems (frontend e2e stories,
# E10-S1), not stubbed ahead of time.

.PHONY: up down logs migrate grants seed test test-backend test-frontend lint arch build

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

migrate:
	docker compose run --rm migrate python -m collectai.bootstrap.cli migrate

grants:
	docker compose run --rm grants

seed:
	docker compose run --rm migrate python -m collectai.bootstrap.cli seed

# MOCK-only, no ANTHROPIC_API_KEY, no network (E1-S5 AC3): every test in
# backend/tests runs against synthetic fixtures and an embedded PostgreSQL
# instance started by the test suite itself.
test: test-backend test-frontend

test-backend:
	cd backend && .venv/Scripts/python -m pytest

test-frontend:
	cd frontend && npm run test:run

lint:
	cd backend && .venv/Scripts/ruff check src tests
	cd backend && .venv/Scripts/mypy src
	cd frontend && npm run lint
	cd frontend && npm run typecheck

arch:
	cd backend && .venv/Scripts/lint-imports
	cd backend && .venv/Scripts/python -m pytest tests/architecture

build:
	docker compose build
