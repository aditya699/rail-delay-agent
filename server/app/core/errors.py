"""Typed application errors and the FastAPI handler that renders them.

Raise these from services; the API layer turns them into a consistent JSON body:
``{"error": {"code": "not_found", "message": "..."}}``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for errors that should reach the client with a clean message."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    """A requested resource does not exist."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """The request clashes with existing state (e.g. the analytics are already rebuilding)."""

    status_code = 409
    code = "conflict"


class NotReadyError(AppError):
    """The history is still loading or the models are still training; try again shortly."""

    status_code = 503
    code = "not_ready"


class LLMError(AppError):
    """The language model call failed or returned something unusable."""

    status_code = 502
    code = "llm_error"


class LLMRefusalError(LLMError):
    """The model declined the request (``stop_reason == "refusal"``)."""

    code = "llm_refusal"


def register_error_handlers(app: FastAPI) -> None:
    """Attach the :class:`AppError` handler to ``app``."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
