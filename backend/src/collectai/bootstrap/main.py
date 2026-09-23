"""Composition root: startup validation, plus the ASGI entrypoint (E1-S5).

This module is layer 8 (`bootstrap`) and wires `config.settings` and
`config.policy` together, failing closed if either is invalid, satisfying
AC2/AC3/AC7 ("the application fails to start with a named error"). It does
not wire RBAC or any router beyond `system` — later stories (starting with
the `api` layer's E3-S1) extend `api/app.py` itself, not this module.

`run_startup_validation` stays free of import-time side effects (existing
tests import it directly via `from collectai.bootstrap.main import
run_startup_validation`, which executes this whole module body on import).
The ASGI app is therefore exposed as the factory function `build_app`, not a
bare module-level `app = ...`: `uvicorn collectai.bootstrap.main:build_app
--factory` (used by `backend/Dockerfile` and `docker-compose.yml`'s `api`
service) calls it only when the server actually starts, so importing this
module for its startup-validation slice never triggers a real startup
validation against `os.environ` as an import side effect.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from collectai.api.app import create_app
from collectai.config.policy.loader import (
    SEED_POLICY_V1_PATH,
    SEED_POLICY_V1_VERSION,
    PolicyFileNotFoundError,
    load_policy_rule_set_from_file,
)
from collectai.config.policy.provider import PolicyProvider
from collectai.config.policy.validator import PolicyValidationError
from collectai.config.settings import Settings, StartupConfigError, load_settings
from collectai.types.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StartupValidationResult:
    """Everything startup validation produced: validated settings and an
    activated `PolicyProvider`, ready for later layers to consume."""

    settings: Settings
    policy_provider: PolicyProvider


def run_startup_validation(
    *,
    env: Mapping[str, str] | None = None,
    clock: Clock | None = None,
    policy_file_path: Path = SEED_POLICY_V1_PATH,
    policy_version: str = SEED_POLICY_V1_VERSION,
) -> StartupValidationResult:
    """Load and validate settings and the seed PolicyRuleSet; fail closed.

    Raises `collectai.config.settings.StartupConfigError` for an invalid
    environment variable, or `collectai.config.policy.validator.PolicyValidationError`
    / `collectai.config.policy.loader.PolicyFileNotFoundError` for an invalid
    or missing policy seed file. On any failure, no partial state is
    returned — the caller (and, in later stories, the process) must not start.
    """
    active_clock = clock if clock is not None else SystemClock()

    try:
        settings = load_settings(env)
    except StartupConfigError as exc:
        logger.error(
            "Startup validation failed: invalid configuration",
            extra={"parameter": exc.parameter, "reason": exc.reason},
        )
        raise

    provider = PolicyProvider()
    try:
        rule_set = load_policy_rule_set_from_file(
            policy_file_path, policy_version=policy_version, clock=active_clock
        )
    except (PolicyValidationError, PolicyFileNotFoundError) as exc:
        logger.error(
            "Startup validation failed: invalid PolicyRuleSet",
            extra={"policy_version": policy_version, "error": str(exc)},
        )
        raise
    provider.register(rule_set)
    provider.activate(policy_version, active_clock)

    logger.info(
        "Startup validation succeeded",
        extra={"llm_mode": settings.llm_mode.value, "policy_version": policy_version},
    )
    return StartupValidationResult(settings=settings, policy_provider=provider)


def build_app() -> FastAPI:
    """ASGI entrypoint factory (E1-S5 AC1, AC2). Runs full startup
    validation (fail closed) and builds the FastAPI app from the resulting
    `Settings` and already-activated `PolicyProvider`, so the seed policy
    file is loaded and validated exactly once. Called by uvicorn via
    `--factory`, never at import time."""
    result = run_startup_validation()
    return create_app(result.settings, policy_provider=result.policy_provider)
