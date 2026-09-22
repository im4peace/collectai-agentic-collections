"""Shared SQLAlchemy 2.0 declarative base for every ORM table module."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class. All ORM entity classes inherit from this."""
