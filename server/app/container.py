"""Composition root: build every long-lived object once and wire them together.

Routes reach these through :mod:`app.api.deps`; tests build a container with the demo
LLM, a fixed live clock and a temporary database instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.chat import ChatAgent
from app.core.catalog import Catalog
from app.core.config import Settings
from app.db.session import build_engine, build_session_factory, create_schema
from app.ingest.live import LiveSource, RunningStatusApiSource, SimClock, SimulatedLiveSource
from app.llm import build_llm
from app.llm.base import LLMClient
from app.services.analytics import AnalyticsService
from app.services.history import HistoryService
from app.services.live import LiveService
from app.services.tasks import TaskRunner

REPLAY_FILE = "live_replay.csv"


@dataclass
class Container:
    settings: Settings
    catalog: Catalog
    engine: Engine
    session_factory: sessionmaker[Session]
    llm: LLMClient
    runner: TaskRunner
    history: HistoryService
    analytics: AnalyticsService
    live: LiveService
    chat: ChatAgent


def build_source(settings: Settings, catalog: Catalog) -> LiveSource:
    """The live source selected by ``LIVE_SOURCE``."""
    if settings.live_source == "http":
        if not settings.running_status_api_url:
            raise ValueError(
                "LIVE_SOURCE=http needs RUNNING_STATUS_API_URL (see docs/data-sources.md)."
            )
        key = settings.running_status_api_key
        return RunningStatusApiSource(
            base_url=settings.running_status_api_url,
            api_key=key.get_secret_value() if key else None,
            network=catalog.network,
            timeout=settings.running_status_timeout,
            user_agent=settings.http_user_agent,
        )
    clock = SimClock(settings.live_start, settings.live_speed)
    return SimulatedLiveSource(settings.samples_dir / REPLAY_FILE, clock)


def build_container(
    settings: Settings, llm: LLMClient | None = None, source: LiveSource | None = None
) -> Container:
    """Create folders, the schema, the LLM client, the live source and the services."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    catalog = Catalog(settings.config_dir)

    engine = build_engine(settings.sqlalchemy_url)
    create_schema(engine)
    session_factory = build_session_factory(engine)

    llm = llm or build_llm(settings, catalog)
    analytics = AnalyticsService(engine, catalog)
    live = LiveService(
        session_factory=session_factory,
        source=source or build_source(settings, catalog),
        network=catalog.network,
        analytics=analytics,
        poll_seconds=settings.live_poll_seconds,
    )
    chat = ChatAgent(
        llm=llm,
        catalog=catalog,
        live=live,
        analytics=analytics,
        intent_effort=settings.intent_effort,
        model_label=settings.model_label,
    )
    return Container(
        settings=settings,
        catalog=catalog,
        engine=engine,
        session_factory=session_factory,
        llm=llm,
        runner=TaskRunner(),
        history=HistoryService(session_factory, catalog.network),
        analytics=analytics,
        live=live,
        chat=chat,
    )
