"""Pure-logic tests for `domain_services.portfolio_service`'s filter, sort
and paginate helpers (E3-S2 AC2, AC3).

`filter_by_priority_band`, `sort_portfolio_rows` and `paginate_portfolio_rows`
all operate on `PortfolioRow` -- a plain dataclass, no ORM or FastAPI types
-- so these tests build rows directly and never touch a database
(code-gen skill: "only mock external boundaries"; there is no boundary to
mock here at all). `tests/api/test_e3_s2_portfolio_filter_sort.py` covers
the same behaviour end to end against a real, migrated Postgres database
through the actual `GET /api/portfolio` endpoint.
"""

from __future__ import annotations

from decimal import Decimal

from collectai.domain_services.portfolio_service import (
    PortfolioRow,
    filter_by_priority_band,
    paginate_portfolio_rows,
    sort_portfolio_rows,
)
from collectai.types.enums import AccountType, Bucket, CollectionStatus, PriorityBand
from collectai.types.money import Money


def _row(
    *,
    account_id: str,
    customer_name: str = "Priya Chandrasekaran",
    overdue_amount: str = "500.00",
    dpd: int = 30,
    priority_band: PriorityBand = PriorityBand.MEDIUM,
    priority_score: str = "50.00",
    collection_status: CollectionStatus = CollectionStatus.IN_PROGRESS,
) -> PortfolioRow:
    return PortfolioRow(
        account_id=account_id,
        customer_id="cus_000101",
        customer_name=customer_name,
        account_type=AccountType.PERSONAL_LOAN,
        outstanding_balance=Money("9000.00"),
        overdue_amount=Money(overdue_amount),
        dpd=dpd,
        bucket=Bucket.DPD_30_59,
        collection_status=collection_status,
        priority_band=priority_band,
        priority_score=Decimal(priority_score),
        human_treatment=False,
        automated_treatment_suppressed=False,
        record_version=3,
    )


# ---------------------------------------------------------------------------
# filter_by_priority_band
# ---------------------------------------------------------------------------


def test_filter_by_priority_band_returns_only_rows_in_the_requested_bands() -> None:
    low = _row(account_id="acc_000101", priority_band=PriorityBand.LOW)
    medium = _row(account_id="acc_000102", priority_band=PriorityBand.MEDIUM)
    high = _row(account_id="acc_000103", priority_band=PriorityBand.HIGH)

    result = filter_by_priority_band([low, medium, high], [PriorityBand.HIGH, PriorityBand.LOW])

    assert result == [low, high]


def test_filter_by_priority_band_returns_all_rows_when_no_bands_requested() -> None:
    rows = [
        _row(account_id="acc_000101", priority_band=PriorityBand.LOW),
        _row(account_id="acc_000102", priority_band=PriorityBand.HIGH),
    ]

    assert filter_by_priority_band(rows, None) == rows
    assert filter_by_priority_band(rows, []) == rows


def test_filter_by_priority_band_returns_empty_when_no_row_matches() -> None:
    rows = [_row(account_id="acc_000101", priority_band=PriorityBand.LOW)]

    assert filter_by_priority_band(rows, [PriorityBand.HIGH]) == []


# ---------------------------------------------------------------------------
# sort_portfolio_rows
# ---------------------------------------------------------------------------


def test_sort_portfolio_rows_orders_by_overdue_amount_ascending_using_decimal_amounts() -> None:
    lowest = _row(account_id="acc_000101", overdue_amount="120.34")
    middle = _row(account_id="acc_000102", overdue_amount="770.40")
    highest = _row(account_id="acc_000103", overdue_amount="2999.99")

    result = sort_portfolio_rows(
        [highest, lowest, middle], sort_by="overdue_amount", sort_dir="asc"
    )

    assert [row.account_id for row in result] == ["acc_000101", "acc_000102", "acc_000103"]


def test_sort_portfolio_rows_orders_by_overdue_amount_descending() -> None:
    lowest = _row(account_id="acc_000101", overdue_amount="120.34")
    middle = _row(account_id="acc_000102", overdue_amount="770.40")
    highest = _row(account_id="acc_000103", overdue_amount="2999.99")

    result = sort_portfolio_rows(
        [lowest, middle, highest], sort_by="overdue_amount", sort_dir="desc"
    )

    assert [row.account_id for row in result] == ["acc_000103", "acc_000102", "acc_000101"]


def test_sort_portfolio_rows_orders_by_dpd_ascending_and_descending() -> None:
    fresh = _row(account_id="acc_000101", dpd=5)
    mid = _row(account_id="acc_000102", dpd=45)
    old = _row(account_id="acc_000103", dpd=95)

    ascending = sort_portfolio_rows([old, fresh, mid], sort_by="dpd", sort_dir="asc")
    descending = sort_portfolio_rows([old, fresh, mid], sort_by="dpd", sort_dir="desc")

    assert [row.account_id for row in ascending] == ["acc_000101", "acc_000102", "acc_000103"]
    assert [row.account_id for row in descending] == ["acc_000103", "acc_000102", "acc_000101"]


def test_sort_portfolio_rows_orders_by_priority_score() -> None:
    low_score = _row(account_id="acc_000101", priority_score="12.50")
    high_score = _row(account_id="acc_000102", priority_score="88.00")

    result = sort_portfolio_rows(
        [low_score, high_score], sort_by="priority_score", sort_dir="desc"
    )

    assert [row.account_id for row in result] == ["acc_000102", "acc_000101"]


def test_sort_portfolio_rows_breaks_ties_by_account_id_ascending_when_sorting_ascending() -> None:
    tied_b = _row(account_id="acc_000102", overdue_amount="500.00")
    tied_a = _row(account_id="acc_000101", overdue_amount="500.00")
    tied_c = _row(account_id="acc_000103", overdue_amount="500.00")

    result = sort_portfolio_rows(
        [tied_c, tied_b, tied_a], sort_by="overdue_amount", sort_dir="asc"
    )

    assert [row.account_id for row in result] == ["acc_000101", "acc_000102", "acc_000103"]


def test_sort_portfolio_rows_breaks_ties_by_account_id_ascending_when_sorting_descending() -> None:
    """api-contracts.md 3.3: "Ties break by account_id asc" -- independent
    of `sort_dir`, so a descending sort still lists tied rows account_id
    ascending, not descending."""
    tied_b = _row(account_id="acc_000102", overdue_amount="500.00")
    tied_a = _row(account_id="acc_000101", overdue_amount="500.00")
    tied_c = _row(account_id="acc_000103", overdue_amount="500.00")

    result = sort_portfolio_rows(
        [tied_c, tied_b, tied_a], sort_by="overdue_amount", sort_dir="desc"
    )

    assert [row.account_id for row in result] == ["acc_000101", "acc_000102", "acc_000103"]


# ---------------------------------------------------------------------------
# paginate_portfolio_rows
# ---------------------------------------------------------------------------


def test_paginate_portfolio_rows_slices_by_limit_and_offset() -> None:
    rows = [_row(account_id=f"acc_00010{i}") for i in range(5)]

    page = paginate_portfolio_rows(rows, limit=2, offset=1)

    assert [row.account_id for row in page] == ["acc_000101", "acc_000102"]


def test_paginate_portfolio_rows_returns_empty_when_offset_is_beyond_the_last_row() -> None:
    rows = [_row(account_id="acc_000101")]

    assert paginate_portfolio_rows(rows, limit=50, offset=10) == []


def test_paginate_portfolio_rows_returns_remaining_rows_when_limit_exceeds_remaining() -> None:
    rows = [_row(account_id=f"acc_00010{i}") for i in range(3)]

    page = paginate_portfolio_rows(rows, limit=200, offset=1)

    assert [row.account_id for row in page] == ["acc_000101", "acc_000102"]
