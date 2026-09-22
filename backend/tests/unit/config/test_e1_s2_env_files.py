"""Tests that .env is git-ignored and .env.example lists every required key (AC8)."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]

_REQUIRED_ENV_KEYS = [
    "LLM_MODE",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_API_KEY",
    "TOOL_CALL_CAP_PER_TURN",
    "AI_RETRY_BOUND",
    "MAX_CLARIFICATION_TURNS",
    "CHAT_RATE_LIMIT_PER_MINUTE",
    "API_RATE_LIMIT_PER_MINUTE",
    "PROVIDER_TIMEOUT_SECONDS",
    "PROPOSAL_TTL_MINUTES",
    "DEMO_CONTROLS_ENABLED",
    "DATABASE_URL",
]


def test_gitignore_excludes_env_files() -> None:
    gitignore_text = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore_text.splitlines()


def test_env_example_lists_every_required_configuration_key() -> None:
    env_example_text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for key in _REQUIRED_ENV_KEYS:
        assert f"{key}=" in env_example_text, f"{key} missing from .env.example"


def test_env_example_never_uses_a_real_looking_anthropic_model_id() -> None:
    env_example_text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in env_example_text.splitlines():
        if line.startswith("ANTHROPIC_MODEL="):
            value = line.split("=", 1)[1]
            assert "REPLACE_ME" in value


def test_env_example_never_contains_a_real_looking_secret() -> None:
    env_example_text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in env_example_text.splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            value = line.split("=", 1)[1]
            assert "REPLACE_ME" in value
