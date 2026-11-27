"""Declarative base shared by every ORM model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Timezone-aware 'now' used for created/updated timestamps."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base."""
