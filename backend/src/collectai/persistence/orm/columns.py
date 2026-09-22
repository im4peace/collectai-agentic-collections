"""Shared, non-Money column type constant reused across ORM table modules."""

from __future__ import annotations

from sqlalchemy import DateTime

TIMESTAMPTZ = DateTime(timezone=True)
