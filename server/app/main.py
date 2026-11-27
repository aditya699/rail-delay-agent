"""FastAPI entry point: ``uv run uvicorn app.main:app --reload``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.container import build_container
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.ingest.live import LiveSource
from app.llm.base import LLMClient
from app.services.demo import prepare, seed_demo

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    source: LiveSource | None = None,
) -> FastAPI:
    """Build the FastAPI app. Tests pass their own settings, a FakeLLM and a fixed clock."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings, llm, source)
        app.state.container = container
        container.runner.bind(asyncio.get_running_loop())
        # In the background, so the API answers (and /health shows progress) while the
        # history loads and the models train.
        startup = seed_demo(container) if settings.seed_demo else prepare(container)
        container.runner.submit(startup, name="startup")
        container.live.start()
        logger.info(
            "%s ready (LLM: %s, model: %s, live source: %s, poll every %ss)",
            settings.app_name,
            settings.llm_provider,
            settings.model_label,
            container.live.source.name,
            settings.live_poll_seconds or "off",
        )
        yield
        await container.live.stop()
        await container.runner.shutdown()
        container.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Live train running status with a history badge and a p50-p90 arrival forecast, "
            "a chatbot that answers in English or Hinglish from computed facts only, and "
            "delay patterns: where trains add delay, in which months and at which hours."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
