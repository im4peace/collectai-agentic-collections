"""Composition root: startup validation (partial file).

This module is layer 8 (`bootstrap`) and is deliberately narrow for E1-S2: it
wires `config.settings` and `config.policy` together and fails closed if
either is invalid, satisfying AC2/AC3/AC7 ("the application fails to start
with a named error"). It does not build an ASGI `app` object or wire
FastAPI — a later story (the `api` layer) extends this module to do that.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
