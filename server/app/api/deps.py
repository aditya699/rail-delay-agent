"""FastAPI dependencies: reach the container and open a database session per request."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.container import Container
from app.db.session import session_scope


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_session(container: Annotated[Container, Depends(get_container)]) -> Iterator[Session]:
    """A session that commits when the request succeeds."""
    with session_scope(container.session_factory) as session:
        yield session


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[Session, Depends(get_session)]
