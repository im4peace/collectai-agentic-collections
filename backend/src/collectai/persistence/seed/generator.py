"""Deterministic synthetic seed data generation (data-models.md section 6, AC1).

Generates `SeedDataset` in-memory only; nothing here touches a database
session (that is `load_seed_dataset`'s job, using the repositories' idempotent
`bulk_upsert_ignore_conflicts`, called from `bootstrap/cli.py`). Deterministic
from a fixed `random.Random` seed: the same `(account_count, random_seed)`
always produces byte-identical rows, which is what makes the loader's
`INSERT ... ON CONFLICT DO NOTHING` idempotent across repeated runs (AC1).
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.repositories.account_repository import AccountRepository
from collectai.persistence.repositories.customer_repository import CustomerRepository
from collectai.persistence.repositories.delinquency_repository import DelinquencyRecordRepository
from collectai.persistence.repositories.delinquent_item_repository import DelinquentItemRepository
from collectai.persistence.repositories.interaction_repository import InteractionRepository
from collectai.persistence.repositories.promise_to_pay_repository import PromiseToPayRepository
from collectai.persistence.seed.builders import (
    build_account,
    build_customer,
    build_delinquency_record,
    build_delinquent_items,
    build_interactions,
    build_prior_ptp,
    sample_dpd,
)
from collectai.persistence.seed.models import SeedDataset

MIN_ACCOUNT_COUNT = 200
MAX_ACCOUNT_COUNT = 1000
DEFAULT_ACCOUNT_COUNT = 500
DEFAULT_RANDOM_SEED = 20260922
_PRIOR_PTP_FRACTION = 0.12
SEED_POLICY_VERSION = "policy-v1"

_SEED_NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


class InvalidAccountCountError(ValueError):
    """Raised when `account_count` is outside the [200, 1000] contract range."""

    def __init__(self, account_count: int) -> None:
        self.account_count = account_count
        super().__init__(
            f"account_count must be between {MIN_ACCOUNT_COUNT} and {MAX_ACCOUNT_COUNT}, "
            f"got {account_count}"
        )


def generate_seed_dataset(
    *,
    account_count: int = DEFAULT_ACCOUNT_COUNT,
    random_seed: int = DEFAULT_RANDOM_SEED,
    now: datetime = _SEED_NOW,
) -> SeedDataset:
    """Generate `account_count` synthetic customers and accounts (both CARD
    and PERSONAL_LOAN), 1-3 delinquent items each, 0-5 interactions, and a
    small fraction with a prior PTP (some BROKEN)."""
    if not MIN_ACCOUNT_COUNT <= account_count <= MAX_ACCOUNT_COUNT:
        raise InvalidAccountCountError(account_count)

    rng = random.Random(random_seed)
    dataset = SeedDataset()
    for index in range(1, account_count + 1):
        _generate_one_account(dataset, index=index, now=now, rng=rng)
    return dataset


def _generate_one_account(
    dataset: SeedDataset, *, index: int, now: datetime, rng: random.Random
) -> None:
    customer_id = f"cus_{index:06d}"
    account_id = f"acc_{index:06d}"
    account_type = "CARD" if index % 2 == 0 else "PERSONAL_LOAN"

    dataset.customers.append(build_customer(customer_id, index, now))
    dataset.accounts.append(build_account(account_id, customer_id, account_type, now, rng))

    dpd = sample_dpd(rng)
    items, overdue_amount = build_delinquent_items(
        account_id, customer_id, rng.randint(1, 3), rng, index
    )
    dataset.delinquent_items.extend(items)
    dataset.delinquency_records.append(
        build_delinquency_record(
            account_id, customer_id, overdue_amount=overdue_amount, dpd=dpd, now=now, rng=rng
        )
    )
    dataset.interactions.extend(
        build_interactions(account_id, customer_id, rng.randint(0, 5), rng, now, index)
    )
    if rng.random() < _PRIOR_PTP_FRACTION:
        dataset.promise_to_pays.append(build_prior_ptp(account_id, customer_id, rng, now, index))


async def load_seed_dataset(
    session: AsyncSession, dataset: SeedDataset, *, now: datetime = _SEED_NOW
) -> dict[str, int]:
    """Idempotently load a validated `SeedDataset`: `INSERT ... ON CONFLICT
    DO NOTHING` on the deterministic ids (AC1), so running the seed twice
    inserts zero rows the second time. Returns rows-actually-inserted per
    table; callers pass only rows that passed `seed.validator` first."""
    await _ensure_seed_policy_rule_set_row(session, now=now)
    inserted = {
        "customer": await CustomerRepository().bulk_upsert_ignore_conflicts(
            session, dataset.customers
        ),
        "account": await AccountRepository().bulk_upsert_ignore_conflicts(
            session, dataset.accounts, pk_columns=["account_id"]
        ),
        "delinquency_record": await DelinquencyRecordRepository().bulk_upsert_ignore_conflicts(
            session, dataset.delinquency_records, pk_columns=["account_id"]
        ),
        "delinquent_item": await DelinquentItemRepository().bulk_upsert_ignore_conflicts(
            session, dataset.delinquent_items, pk_columns=["item_id"]
        ),
        "interaction": await InteractionRepository().bulk_upsert_ignore_conflicts(
            session, dataset.interactions, pk_columns=["interaction_id"]
        ),
        "promise_to_pay": await PromiseToPayRepository().bulk_upsert_ignore_conflicts(
            session, dataset.promise_to_pays, pk_columns=["ptp_id"]
        ),
    }
    await session.commit()
    return inserted


async def _ensure_seed_policy_rule_set_row(session: AsyncSession, *, now: datetime) -> None:
    """Seed PromiseToPay rows carry `policy_version = 'policy-v1'`, which is
    FK-constrained to `policy_rule_set` (data-models.md section 1). Policy
    activation itself stays in-memory (E1-S2's `PolicyProvider`; out of
    scope here), but the seed loader still needs a matching row to satisfy
    referential integrity, so it inserts a minimal placeholder, idempotently.
    `now` is always caller-supplied (the injected Clock), never SQL `now()`."""
    await session.execute(
        text(
            "INSERT INTO policy_rule_set "
            "(policy_version, parameters, content_hash, is_active, created_at) "
            "VALUES (:version, '{}'::jsonb, "
            "'0000000000000000000000000000000000000000000000000000000000000000', "
            "true, :created_at) "
            "ON CONFLICT (policy_version) DO NOTHING"
        ),
        {"version": SEED_POLICY_VERSION, "created_at": now},
    )
