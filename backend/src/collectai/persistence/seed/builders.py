"""Per-entity row builders used by `seed/generator.py`.

Split out from `generator.py` (Rule 4, learned-rules.md) so the orchestration
loop stays short and each entity's synthetic-data shape is independently
readable and testable. Every generated value is fictional: names are
templated, emails are `*@example.com`, phones are `+1-555-01xx`
(CLAUDE.md: synthetic data only).

NOTE: past the 200-line warning threshold (code-gen skill principle #1);
consider splitting per-entity builder groups (customer/account, PTP/payment,
hardship/dispute/escalation) into submodules re-exported from here if this
file grows further.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

from collectai.types.money import Money

_FIRST_NAMES: tuple[str, ...] = ("Avery", "Riley", "Jordan", "Morgan", "Casey", "Rowan", "Skyler")
_LAST_NAMES: tuple[str, ...] = ("Nakamura", "Delgado", "Okafor", "Petrov", "Lindqvist", "Haddad")
_DPD_BUCKET_RANGES: tuple[tuple[int, int, str], ...] = (
    (0, 0, "CURRENT"),
    (1, 29, "DPD_1_29"),
    (30, 59, "DPD_30_59"),
    (60, 89, "DPD_60_89"),
    (90, 180, "DPD_90_PLUS"),
)
_ITEM_KINDS: tuple[str, ...] = ("INSTALLMENT", "STATEMENT_CYCLE", "FEE_OR_CHARGE")
_INTERACTION_CHANNELS: tuple[str, ...] = (
    "SIMULATED_CHAT",
    "SIMULATED_OUTBOUND_CALL",
    "SIMULATED_OUTBOUND_MESSAGE",
    "SYSTEM_EVENT",
)
_CONTACT_OUTCOMES: tuple[str, ...] = (
    "NO_CONTACT",
    "CONTACT_NO_COMMITMENT",
    "PTP_MADE",
    "PTP_BROKEN",
    "PAYMENT_MADE",
)


def bucket_for_dpd(dpd: int) -> str:
    for low, high, bucket in _DPD_BUCKET_RANGES:
        if low <= dpd <= high:
            return bucket
    return "DPD_90_PLUS"


def sample_dpd(rng: random.Random) -> int:
    low, high, _ = rng.choice(_DPD_BUCKET_RANGES)
    return rng.randint(low, high)


def build_customer(customer_id: str, index: int, now: datetime) -> dict[str, Any]:
    first = _FIRST_NAMES[index % len(_FIRST_NAMES)]
    last = _LAST_NAMES[index % len(_LAST_NAMES)]
    return {
        "customer_id": customer_id,
        "display_name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{index}@example.com",
        "phone": f"+1-555-01{index % 100:02d}",
        "vulnerability_flag": False,
        "vulnerability_category": None,
        "vulnerability_case_id": None,
        "created_at": now,
        "updated_at": now,
    }


def build_account(
    account_id: str, customer_id: str, account_type: str, now: datetime, rng: random.Random
) -> dict[str, Any]:
    if account_type == "CARD":
        product_attributes = {
            "credit_limit": str(Money(str(rng.randint(1000, 15000)))),
            "minimum_payment_due": str(Money(str(rng.randint(25, 300)))),
        }
        product_name = "Everyday Card"
    else:
        product_attributes = {
            "original_principal": str(Money(str(rng.randint(2000, 40000)))),
            "term_months": str(rng.choice((12, 24, 36, 48, 60))),
            "monthly_installment": str(Money(str(rng.randint(100, 900)))),
        }
        product_name = "Everyday Personal Loan"
    return {
        "account_id": account_id,
        "customer_id": customer_id,
        "account_type": account_type,
        "product_name": product_name,
        "currency": "USD",
        "opened_on": now.date() - timedelta(days=rng.randint(60, 900)),
        "product_attributes": product_attributes,
        "created_at": now,
    }


def build_delinquent_items(
    account_id: str, customer_id: str, item_count: int, rng: random.Random, base_index: int
) -> tuple[list[dict[str, Any]], Money]:
    items: list[dict[str, Any]] = []
    total = Money("0")
    for slot in range(item_count):
        amount = Money(str(rng.randint(20, 800)))
        total = Money(str(total.amount + amount.amount))
        items.append(
            {
                "item_id": f"itm_{base_index:06d}{slot}",
                "account_id": account_id,
                "customer_id": customer_id,
                "kind": _ITEM_KINDS[slot % len(_ITEM_KINDS)],
                "label": f"{_ITEM_KINDS[slot % len(_ITEM_KINDS)].title()} item {slot + 1}",
                "amount_outstanding": amount,
                "due_date": date(2026, 8, 1) - timedelta(days=rng.randint(0, 60)),
                "status": "OPEN",
            }
        )
    return items, total


def build_delinquency_record(
    account_id: str,
    customer_id: str,
    *,
    overdue_amount: Money,
    dpd: int,
    now: datetime,
    rng: random.Random,
) -> dict[str, Any]:
    outstanding_balance = Money(str(overdue_amount.amount + rng.randint(200, 9000)))
    collection_status = "PTP_PENDING" if rng.random() < 0.15 else "IN_PROGRESS"
    return {
        "account_id": account_id,
        "customer_id": customer_id,
        "outstanding_balance": outstanding_balance,
        "overdue_amount": overdue_amount,
        "dpd": dpd,
        "bucket": bucket_for_dpd(dpd),
        "collection_status": collection_status,
        "as_of": now,
        "record_version": 1,
        "updated_at": now,
    }


def build_interactions(
    account_id: str,
    customer_id: str,
    count: int,
    rng: random.Random,
    now: datetime,
    base_index: int,
) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    for slot in range(count):
        interactions.append(
            {
                "interaction_id": f"int_{base_index:06d}{slot}",
                "account_id": account_id,
                "customer_id": customer_id,
                "channel": rng.choice(_INTERACTION_CHANNELS),
                "direction": rng.choice(("INBOUND", "OUTBOUND")),
                "outcome": rng.choice(_CONTACT_OUTCOMES),
                "occurred_at": now - timedelta(days=rng.randint(1, 90)),
                "summary": "Simulated contact event.",
                "counts_as_attempt": rng.random() < 0.8,
                "conversation_id": None,
            }
        )
    return interactions


def build_prior_ptp(
    account_id: str, customer_id: str, rng: random.Random, now: datetime, base_index: int
) -> dict[str, Any]:
    """A small fraction of accounts carry a prior PTP (some BROKEN) so the
    priority factors vary, per data-models.md section 6."""
    is_broken = rng.random() < 0.4
    status = "BROKEN" if is_broken else "KEPT"
    promised_amount = Money(str(rng.randint(50, 500)))
    return {
        "ptp_id": f"ptp_{base_index:06d}",
        "account_id": account_id,
        "customer_id": customer_id,
        "item_id": None,
        "promised_amount": promised_amount,
        "promised_date": now.date() - timedelta(days=rng.randint(1, 20)),
        "status": status,
        "cumulative_paid": Money("0.00") if is_broken else promised_amount,
        "interaction_reference": None,
        "source": "OFFICER_MANUAL",
        "created_by_persona": "COLLECTIONS_OFFICER",
        "created_at": now - timedelta(days=30),
        "updated_at": now,
        "kept_at": now if not is_broken else None,
        "broken_at": now if is_broken else None,
        "cancelled_at": None,
        "cancel_reason": None,
        "policy_version": "policy-v1",
        "version": 1,
    }
