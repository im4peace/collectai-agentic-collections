"""Loads a `PolicyRuleSet` from a JSON seed file through the contract validator.

The seed file (`policy-v1.json`) holds only the `PolicyParameters` payload
(the `priority`, `ptp`, ... sections); this module wraps that payload into a
full `PolicyRuleSet` with its version, content hash and `Clock`-derived
`created_at`. A loaded rule set always starts inactive (`is_active=False`,
`activated_at=None`) — activation is `PolicyProvider`'s responsibility.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

from collectai.config.policy.models import PolicyRuleSet, compute_content_hash
from collectai.config.policy.validator import PolicyValidationError, validate_policy_parameters
from collectai.types.clock import Clock

logger = logging.getLogger(__name__)

SEED_POLICY_V1_PATH: Final[Path] = Path(__file__).resolve().parent / "policy-v1.json"
SEED_POLICY_V1_VERSION: Final[str] = "policy-v1"


class PolicyFileNotFoundError(Exception):
    """Raised when the PolicyRuleSet seed file does not exist on disk."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        super().__init__(f"PolicyRuleSet file not found: {file_path}")


def load_policy_rule_set_from_file(
    file_path: Path, *, policy_version: str, clock: Clock
) -> PolicyRuleSet:
    """Load, parse and validate a `PolicyRuleSet` from a JSON file.

    Raises `PolicyFileNotFoundError` if `file_path` does not exist, or
    `PolicyValidationError` naming the offending parameter if the JSON is
    malformed or fails the policy contract. Never partially applied: on
    failure, no `PolicyRuleSet` is constructed.
    """
    if not file_path.is_file():
        logger.error(
            "Policy rule set file not found",
            extra={"policy_version": policy_version, "file_path": str(file_path)},
        )
        raise PolicyFileNotFoundError(file_path)

    raw_text = file_path.read_text(encoding="utf-8")
    raw_parameters = _parse_json(raw_text, file_path)
    parameters = validate_policy_parameters(raw_parameters)
    content_hash = compute_content_hash(parameters)

    logger.info(
        "Policy rule set loaded",
        extra={"policy_version": policy_version, "content_hash": content_hash},
    )
    return PolicyRuleSet(
        policy_version=policy_version,
        parameters=parameters,
        content_hash=content_hash,
        is_active=False,
        created_at=clock.now(),
        activated_at=None,
    )


def _parse_json(raw_text: str, file_path: Path) -> object:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(
            "Policy rule set file is not valid JSON",
            extra={"file_path": str(file_path), "error": str(exc)},
        )
        raise PolicyValidationError(parameter="<root>", reason=f"Invalid JSON: {exc}") from exc


def load_seed_policy_v1(clock: Clock) -> PolicyRuleSet:
    """Load the seeded `policy-v1` rule set shipped with the package."""
    return load_policy_rule_set_from_file(
        SEED_POLICY_V1_PATH, policy_version=SEED_POLICY_V1_VERSION, clock=clock
    )
