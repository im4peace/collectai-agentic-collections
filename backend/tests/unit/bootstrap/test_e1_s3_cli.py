"""Unit tests for `collectai.bootstrap.cli` (E1-S3): argument parsing, the
migrate/seed dispatch, and the fail-closed startup-config and
seed-validation-failure paths. No database is touched here — `run_migrate`
and `run_seed` are monkeypatched at the call site, since their own
underlying behaviour (Alembic upgrade, seed generation/validation/loading)
is already covered by `bt/db/test_e1_s3_*` against a real embedded Postgres.
"""

from __future__ import annotations

from typing import Any

import pytest

from collectai.bootstrap import cli
from collectai.config.settings import StartupConfigError
from collectai.persistence.seed.generator import DEFAULT_ACCOUNT_COUNT, DEFAULT_RANDOM_SEED
from collectai.persistence.seed.models import SeedDataset, SeedValidationFailure
from collectai.types.enums import LlmMode
from collectai.types.reason_codes import ReasonCode


def _fake_settings(database_url: str = "postgresql+asyncpg://user:pw@localhost/collectai") -> Any:
    from collectai.config.settings import Settings

    return Settings(
        llm_mode=LlmMode.MOCK,
        anthropic_model=None,
        anthropic_api_key=None,
        tool_call_cap_per_turn=5,
        ai_retry_bound=1,
        max_clarification_turns=2,
        chat_rate_limit_per_minute=20,
        api_rate_limit_per_minute=300,
        provider_timeout_seconds=20,
        proposal_ttl_minutes=30,
        demo_controls_enabled=False,
        database_url=database_url,
    )


def test_arg_parser_defaults_seed_command_to_documented_defaults() -> None:
    args = cli._build_arg_parser().parse_args(["seed"])
    assert args.command == "seed"
    assert args.account_count == DEFAULT_ACCOUNT_COUNT
    assert args.random_seed == DEFAULT_RANDOM_SEED


def test_arg_parser_accepts_overrides_for_seed_command() -> None:
    args = cli._build_arg_parser().parse_args(
        ["seed", "--account-count", "750", "--random-seed", "99"]
    )
    assert args.account_count == 750
    assert args.random_seed == 99


def test_arg_parser_parses_migrate_command() -> None:
    args = cli._build_arg_parser().parse_args(["migrate"])
    assert args.command == "migrate"


def test_arg_parser_rejects_an_unknown_command() -> None:
    with pytest.raises(SystemExit):
        cli._build_arg_parser().parse_args(["not-a-real-command"])


def test_main_dispatches_migrate_with_the_configured_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "load_settings", lambda: _fake_settings("postgresql+asyncpg://x/y"))
    monkeypatch.setattr(cli, "run_migrate", lambda database_url: calls.append(database_url))

    exit_code = cli.main(["migrate"])

    assert exit_code == 0
    assert calls == ["postgresql+asyncpg://x/y"]


def test_main_dispatches_seed_with_parsed_account_count_and_random_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli, "load_settings", lambda: _fake_settings())

    def fake_run_seed(database_url: str, *, account_count: int, random_seed: int) -> dict[str, int]:
        captured["database_url"] = database_url
        captured["account_count"] = account_count
        captured["random_seed"] = random_seed
        return {"customer": account_count}

    monkeypatch.setattr(cli, "run_seed", fake_run_seed)

    exit_code = cli.main(["seed", "--account-count", "250", "--random-seed", "3"])

    assert exit_code == 0
    assert captured == {
        "database_url": "postgresql+asyncpg://user:pw@localhost/collectai",
        "account_count": 250,
        "random_seed": 3,
    }


def test_main_returns_one_and_never_reaches_migrate_or_seed_on_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_startup_error() -> Any:
        raise StartupConfigError(parameter="DATABASE_URL", reason="is required")

    calls: list[str] = []
    monkeypatch.setattr(cli, "load_settings", raise_startup_error)
    monkeypatch.setattr(cli, "run_migrate", lambda database_url: calls.append("migrate"))
    monkeypatch.setattr(
        cli, "run_seed", lambda database_url, **kw: calls.append("seed") or {}
    )

    exit_code = cli.main(["migrate"])

    assert exit_code == 1
    assert calls == []


def _empty_dataset() -> SeedDataset:
    return SeedDataset(customers=[], delinquency_records=[], delinquent_items=[])


def test_run_seed_refuses_to_load_when_validation_finds_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "generate_seed_dataset", lambda **kw: _empty_dataset())
    monkeypatch.setattr(
        cli,
        "validate_seed_dataset",
        lambda dataset: [
            SeedValidationFailure(
                entity="delinquency_record",
                entity_id="acc_000001",
                reason_code=ReasonCode.FIELD_INVALID,
                detail="negative balance",
            )
        ],
    )
    load_calls: list[SeedDataset] = []
    monkeypatch.setattr(
        cli, "_load_dataset", lambda database_url, dataset: load_calls.append(dataset)
    )

    with pytest.raises(cli.SeedValidationError, match="1 validation failure"):
        cli.run_seed("postgresql+asyncpg://x/y", account_count=200, random_seed=1)

    assert load_calls == []


def test_run_seed_refuses_to_load_when_the_prohibited_pattern_scan_finds_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "generate_seed_dataset", lambda **kw: _empty_dataset())
    monkeypatch.setattr(cli, "validate_seed_dataset", lambda dataset: [])
    monkeypatch.setattr(
        cli,
        "scan_seed_dataset",
        lambda dataset: [
            SeedValidationFailure(
                entity="customer",
                entity_id="cus_000001",
                reason_code=ReasonCode.FIELD_INVALID,
                detail="email domain is not example.com",
            )
        ],
    )
    load_calls: list[SeedDataset] = []
    monkeypatch.setattr(
        cli, "_load_dataset", lambda database_url, dataset: load_calls.append(dataset)
    )

    with pytest.raises(cli.SeedValidationError, match="1 prohibited-pattern scan failure"):
        cli.run_seed("postgresql+asyncpg://x/y", account_count=200, random_seed=1)

    assert load_calls == []
