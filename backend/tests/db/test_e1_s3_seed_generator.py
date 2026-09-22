"""AC1: seed script loads between 200 and 1,000 synthetic accounts including
both CARD and PERSONAL_LOAN types and is idempotent when run twice."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from collectai.persistence.orm.account import AccountOrm
from collectai.persistence.orm.customer import CustomerOrm
from collectai.persistence.seed.generator import (
    MAX_ACCOUNT_COUNT,
    MIN_ACCOUNT_COUNT,
    InvalidAccountCountError,
    generate_seed_dataset,
    load_seed_dataset,
)
from collectai.persistence.seed.validator import validate_seed_dataset

pytestmark = pytest.mark.db


def test_generator_rejects_account_count_below_200() -> None:
    with pytest.raises(InvalidAccountCountError):
        generate_seed_dataset(account_count=199)


def test_generator_rejects_account_count_above_1000() -> None:
    with pytest.raises(InvalidAccountCountError):
        generate_seed_dataset(account_count=1001)


def test_generator_accepts_the_documented_boundary_counts() -> None:
    generate_seed_dataset(account_count=MIN_ACCOUNT_COUNT)  # must not raise
    generate_seed_dataset(account_count=MAX_ACCOUNT_COUNT)  # must not raise


def test_generator_produces_both_card_and_personal_loan_accounts() -> None:
    dataset = generate_seed_dataset(account_count=200)
    account_types = {row["account_type"] for row in dataset.accounts}
    assert account_types == {"CARD", "PERSONAL_LOAN"}


def test_generator_is_deterministic_for_the_same_seed() -> None:
    first = generate_seed_dataset(account_count=200, random_seed=42)
    second = generate_seed_dataset(account_count=200, random_seed=42)
    assert first.accounts == second.accounts
    assert first.customers == second.customers


def test_generated_dataset_passes_its_own_validator() -> None:
    """The generator's output must be internally consistent (no
    dpd/bucket mismatch, no negative balance, item sums equal overdue)."""
    dataset = generate_seed_dataset(account_count=250)
    failures = validate_seed_dataset(dataset)
    assert failures == []


@pytest.mark.asyncio
async def test_seed_load_is_idempotent_when_run_twice(
    session: AsyncSession, clean_db: None
) -> None:
    dataset = generate_seed_dataset(account_count=200, random_seed=7)
    assert validate_seed_dataset(dataset) == []

    first_run = await load_seed_dataset(session, dataset)
    assert first_run["account"] == 200
    assert first_run["customer"] == 200

    second_run = await load_seed_dataset(session, dataset)
    assert second_run["account"] == 0
    assert second_run["customer"] == 0

    account_count = (
        await session.execute(select(func.count()).select_from(AccountOrm))
    ).scalar_one()
    customer_count = (
        await session.execute(select(func.count()).select_from(CustomerOrm))
    ).scalar_one()
    assert account_count == 200
    assert customer_count == 200
