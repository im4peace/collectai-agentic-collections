"""Structure of the Docker startup order and of the CI workflow.

Docker and GitHub Actions cannot run in the unit suite, so these tests read the YAML and pin the
properties the release-closeout fixes rely on: the database grants run after the migrations and
before the API starts, and the e2e and docker-smoke jobs run their root-level steps from the
repository root. The real behaviour is exercised by the `docker-smoke` and `e2e` CI jobs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]


def _load(relative: str) -> dict[str, Any]:
    loaded = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return _load("docker-compose.yml")["services"]  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return _load(".github/workflows/ci.yml")["jobs"]  # type: ignore[no-any-return]


def _steps_text(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


# ---- docker-compose.yml ---------------------------------------------------------------------


def test_db_initialisation_mounts_the_roles_file_and_the_password_script(
    compose: dict[str, Any],
) -> None:
    volumes = compose["db"]["volumes"]

    assert "./deploy/db/init-roles.sql:/docker-entrypoint-initdb.d/01-init-roles.sql:ro" in volumes
    assert any("02-init-app-passwords.sh" in v for v in volumes)


def test_migrate_runs_after_the_database_is_healthy_and_migrates_then_seeds(
    compose: dict[str, Any],
) -> None:
    migrate = compose["migrate"]

    assert migrate["depends_on"] == {"db": {"condition": "service_healthy"}}
    command = " ".join(migrate["command"])
    assert command.index("cli migrate") < command.index("cli seed")


def test_grants_reapplies_the_same_roles_file_after_migrate_as_the_owner(
    compose: dict[str, Any],
) -> None:
    grants = compose["grants"]
    command = grants["command"]

    assert grants["image"] == "postgres:16"
    assert grants["depends_on"] == {"migrate": {"condition": "service_completed_successfully"}}
    assert "./deploy/db/init-roles.sql:/sql/init-roles.sql:ro" in grants["volumes"]
    assert command[0] == "psql"
    assert command[command.index("-v") + 1] == "ON_ERROR_STOP=1"
    assert command[command.index("-U") + 1] == "collectai_owner"  # never the superuser
    assert command[command.index("-f") + 1] == "/sql/init-roles.sql"
    assert "PGPASSWORD" in grants["environment"]
    assert "COLLECTAI_OWNER_PASSWORD" in grants["environment"]["PGPASSWORD"]


def test_api_starts_only_after_the_grants_have_been_applied(compose: dict[str, Any]) -> None:
    depends_on = compose["api"]["depends_on"]

    assert depends_on == {"grants": {"condition": "service_completed_successfully"}}


def test_the_table_grants_have_one_source_the_roles_file() -> None:
    """No second copy of the privileges: not in another deploy file, and the migrations grant
    only what they always did (`audit_event`, through the guarded helper)."""
    sql_files = [p.name for p in (ROOT / "deploy").rglob("*.sql")]
    assert sql_files == ["init-roles.sql"]

    versions = ROOT / "backend" / "src" / "collectai" / "persistence" / "migrations" / "versions"
    granting = sorted(p.name for p in versions.glob("*.py") if "GRANT" in p.read_text("utf-8"))
    assert granting == ["0007_audit_event.py"]  # its own append-only grants, as before


# ---- .github/workflows/ci.yml ---------------------------------------------------------------


def test_the_workflow_default_directory_is_backend(jobs: dict[str, Any]) -> None:
    workflow = _load(".github/workflows/ci.yml")

    assert workflow["defaults"]["run"]["working-directory"] == "backend"
    assert jobs["frontend"]["defaults"]["run"]["working-directory"] == "frontend"


@pytest.mark.parametrize("name", ["e2e", "docker-smoke"])
def test_root_level_jobs_override_the_backend_default(jobs: dict[str, Any], name: str) -> None:
    job = jobs[name]

    assert job["defaults"]["run"]["working-directory"] == "."
    assert "cp .env.example .env" in _steps_text(job)
    assert "docker compose" in _steps_text(job)
    for step in job["steps"]:
        # the only per-step override allowed in these jobs is the frontend one
        assert step.get("working-directory", "frontend") == "frontend", step


def test_the_e2e_frontend_steps_still_run_in_frontend(jobs: dict[str, Any]) -> None:
    commands = {
        step["run"]: step.get("working-directory")
        for step in jobs["e2e"]["steps"]
        if step.get("run", "").startswith(("npm", "npx"))
    }

    assert commands == {
        "npm ci": "frontend",
        "npx playwright install --with-deps chromium": "frontend",
        "npm run e2e": "frontend",
    }


def test_every_backend_pip_install_uses_the_constraints_file(jobs: dict[str, Any]) -> None:
    installs = [
        (name, step["run"])
        for name, job in jobs.items()
        for step in job["steps"]
        if "pip install" in step.get("run", "")
    ]

    assert len(installs) == 6
    for name, command in installs:
        assert command == 'pip install -c constraints.txt -e ".[dev]"', name
        assert jobs[name].get("defaults") is None, f"{name} must run in the backend default"


def test_docker_smoke_covers_the_startup_sequence_and_always_cleans_up(
    jobs: dict[str, Any],
) -> None:
    job = jobs["docker-smoke"]
    text = _steps_text(job)

    assert job["env"] == {"COMPOSE_FILE": "docker-compose.yml:docker-compose.test.yml"}
    assert "docker compose config -q" in text
    assert "up --build -d db migrate grants api" in text
    assert text.count("api-readiness.sh wait") == 2  # after the fresh start and after the restart
    assert text.count("api-readiness.sh check") == 2
    assert text.count("verify-app-grants.sh") == 2  # after the fresh start and after the restart
    assert "docker compose down\n" in text  # restart keeps the volume ...
    assert "up -d db migrate grants api" in text
    last = job["steps"][-1]
    assert last["if"] == "always()"
    assert last["run"] == "docker compose down -v"  # ... and the job always removes it
    assert any(step.get("if") == "failure()" and "logs" in step["run"] for step in job["steps"])


def test_ci_never_configures_a_live_key_or_a_repository_secret(jobs: dict[str, Any]) -> None:
    workflow = _load(".github/workflows/ci.yml")
    configured = [workflow.get("env", {})]
    for job in jobs.values():
        configured.append(job.get("env", {}))
        configured.extend(step.get("env", {}) for step in job["steps"])

    assert all("ANTHROPIC_API_KEY" not in env for env in configured)
    assert "secrets." not in (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_no_workflow_command_contains_a_literal_backslash_n(jobs: dict[str, Any]) -> None:
    """A shell line continuation written as backslash + `n` instead of backslash + newline made
    the docker-smoke wait steps run `bash -c n ...` and never wait for the API."""
    backslash_n = chr(92) + "n"
    for name, job in jobs.items():
        for step in job["steps"]:
            assert backslash_n not in step.get("run", ""), f"{name}: {step.get('name')}"


def test_the_readiness_waits_use_the_diagnostic_script_and_keep_the_180_second_limit(
    jobs: dict[str, Any],
) -> None:
    wait_name = "Wait for the API to report ready"
    e2e = {s.get("name"): s for s in jobs["e2e"]["steps"]}
    smoke = {s.get("name"): s for s in jobs["docker-smoke"]["steps"]}
    script = (ROOT / "deploy" / "ci" / "api-readiness.sh").read_text(encoding="utf-8")

    assert e2e[wait_name]["run"] == "bash deploy/ci/api-readiness.sh wait"
    assert e2e[wait_name]["env"] == {
        "COMPOSE_CMD": "docker compose -f docker-compose.yml -f docker-compose.test.yml"
    }
    assert smoke[wait_name]["run"] == "bash deploy/ci/api-readiness.sh wait"
    assert smoke["Health and readiness"]["run"] == "bash deploy/ci/api-readiness.sh check"
    assert 'WAIT_SECONDS="${WAIT_SECONDS:-180}"' in script


def test_the_readiness_script_reports_service_logs_and_the_failure_kind_without_a_pipe() -> None:
    script = (ROOT / "deploy" / "ci" / "api-readiness.sh").read_text(encoding="utf-8")

    for service in ("api", "db", "migrate", "grants"):
        assert service in script.split("for service in", 1)[1].split(";", 1)[0]
    for kind in ("API unavailable", "non-2xx HTTP response", "failed check", "malformed"):
        assert kind in script
    assert "app_role_grants" in script
    assert "curl -s -o" in script  # curl's own exit status is captured, never piped
    code_lines = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in code_lines if "curl" in line and " | " in line]
    # nothing prints the environment or the compose configuration (which interpolates it)
    code = "\n".join(code_lines)
    for leak in ("printenv", "compose config", "${COMPOSE[@]}\" config", "docker inspect"):
        assert leak not in code
