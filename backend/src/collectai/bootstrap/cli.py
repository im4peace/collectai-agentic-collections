"""`python -m collectai.bootstrap.cli migrate|seed|break-ptps`.

A thin wrapper: `run_migrate` just points Alembic's `upgrade head` at
`Settings.database_url`, `run_seed` just calls the seed
generator/validator/scanner/loader in sequence, and `break-ptps` (E6-S4
AC4) delegates entirely to `collectai.jobs.ptp_lifecycle_job.run`. No
migration, generation or breakage-rule logic lives in this module.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from collectai.config.settings import StartupConfigError, load_settings
from collectai.jobs.ptp_lifecycle_job import run as run_break_ptps
from collectai.persistence.db import build_engine, build_session_factory, normalize_database_url
from collectai.persistence.seed.generator import (
    DEFAULT_ACCOUNT_COUNT,
    DEFAULT_RANDOM_SEED,
    generate_seed_dataset,
    load_seed_dataset,
)
from collectai.persistence.seed.models import SeedDataset
from collectai.persistence.seed.scanner import scan_seed_dataset
from collectai.persistence.seed.validator import validate_seed_dataset
from collectai.types.clock import SystemClock

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "persistence" / "migrations"


class SeedValidationError(Exception):
    """Raised when generated seed data fails validation or the
    prohibited-pattern scan; the CLI must never load a dataset that failed
    either check (AC3, AC4 are enforced here, not only in tests)."""

    def __init__(self, failure_count: int, kind: str) -> None:
        self.failure_count = failure_count
        self.kind = kind
        super().__init__(f"{failure_count} {kind} failure(s); refusing to load seed data")


def run_migrate(database_url: str) -> None:
    """`alembic upgrade head` against `database_url`."""
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("path_separator", "os")
    config.set_main_option("sqlalchemy.url", normalize_database_url(database_url))
    command.upgrade(config, "head")
    logger.info("Migrations applied", extra={"target": "head"})


def run_seed(database_url: str, *, account_count: int, random_seed: int) -> dict[str, int]:
    """Generate, validate, scan and idempotently load synthetic seed data."""
    dataset = generate_seed_dataset(account_count=account_count, random_seed=random_seed)
    _reject_on_validation_or_scan_failures(dataset)
    return asyncio.run(_load_dataset(database_url, dataset))


def _reject_on_validation_or_scan_failures(dataset: SeedDataset) -> None:
    validation_failures = validate_seed_dataset(dataset)
    if validation_failures:
        raise SeedValidationError(len(validation_failures), "validation")
    scan_findings = scan_seed_dataset(dataset)
    if scan_findings:
        raise SeedValidationError(len(scan_findings), "prohibited-pattern scan")


async def _load_dataset(database_url: str, dataset: SeedDataset) -> dict[str, int]:
    engine = build_engine(database_url)
    try:
        session_factory = build_session_factory(engine)
        async with session_factory() as session:
            return await load_seed_dataset(session, dataset, now=SystemClock().now())
    finally:
        await engine.dispose()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m collectai.bootstrap.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="Apply every migration up to head.")
    seed_parser = subparsers.add_parser("seed", help="Generate and load synthetic seed data.")
    seed_parser.add_argument("--account-count", type=int, default=DEFAULT_ACCOUNT_COUNT)
    seed_parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    subparsers.add_parser(
        "break-ptps", help="Move every overdue, unsatisfied PENDING PTP to BROKEN."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        settings = load_settings()
    except StartupConfigError as exc:
        logger.error(
            "CLI startup failed: invalid configuration",
            extra={"parameter": exc.parameter, "reason": exc.reason},
        )
        return 1

    if args.command == "migrate":
        run_migrate(settings.database_url)
        return 0

    if args.command == "break-ptps":
        result = asyncio.run(run_break_ptps(settings.database_url))
        logger.info(
            "PTP breakage job complete",
            extra={
                "checked": result.checked_count,
                "broken": result.broken_count,
                "kept": result.kept_count,
            },
        )
        return 0

    inserted = run_seed(
        settings.database_url, account_count=args.account_count, random_seed=args.random_seed
    )
    logger.info("Seed data loaded", extra={"inserted": inserted})
    return 0


if __name__ == "__main__":
    sys.exit(main())
