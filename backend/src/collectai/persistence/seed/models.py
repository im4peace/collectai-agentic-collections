"""Typed shapes shared by the seed generator, validator and scanner.

`SeedValidationFailure` mirrors `collectai.types.results.RuleFailure`'s shape
(a stable reason code plus a human-readable detail) rather than inventing an
incompatible parallel pattern, per the E1-S3 brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from collectai.types.reason_codes import ReasonCode


@dataclass(frozen=True, slots=True)
class SeedValidationFailure:
    """A rejected seed record, reported instead of loaded silently (AC3)."""

    reason_code: ReasonCode
    entity: str
    entity_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class SeedDataset:
    """Generated rows, one list of plain dict rows per table. Dict values
    use application types (`Money`, `date`, `datetime`) exactly as the ORM
    `TypeDecorator`s expect, so the same rows go straight into a bulk
    upsert without another conversion step."""

    customers: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    delinquency_records: list[dict[str, Any]] = field(default_factory=list)
    delinquent_items: list[dict[str, Any]] = field(default_factory=list)
    interactions: list[dict[str, Any]] = field(default_factory=list)
    promise_to_pays: list[dict[str, Any]] = field(default_factory=list)
