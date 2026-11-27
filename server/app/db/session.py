"""Engine and session factory.

SQLite keeps the project zero-setup. To move to Postgres, set ``DATABASE_URL``
(e.g. ``postgresql+psycopg://user:pass@localhost/rail``) and install the driver.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


def build_engine(url: str) -> Engine:
    """Create an engine; for SQLite, enable foreign keys, WAL and cross-thread use."""
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # The poller writes while API requests read; WAL lets them overlap.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    """Create all tables (no migrations framework, on purpose; see docs/extending.md)."""
    from app.db import models  # noqa: F401  (import registers the models)

    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open a session that commits on success and rolls back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
