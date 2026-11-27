from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.container import REPLAY_FILE, Container, build_container
from app.core.catalog import Catalog
from app.core.config import Settings
from app.ingest.live import SimClock, SimulatedLiveSource
from app.main import create_app
from app.services.demo import seed_demo

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
CONFIG = Path(__file__).resolve().parents[1] / "app" / "config"
NOON = datetime(2026, 11, 27, 12, 0)
"""Every test reads the live feed at this frozen clock (the simulated source's default start)."""


def make_settings(data_dir: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "data_dir": data_dir,
        "llm_provider": "fake",
        "seed_demo": False,
        "live_poll_seconds": 0,
        "samples_dir": SAMPLES,
        "log_level": "WARNING",
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def frozen_source(at: datetime = NOON) -> SimulatedLiveSource:
    """The sample replay with a clock that does not move."""
    return SimulatedLiveSource(SAMPLES / REPLAY_FILE, SimClock(at, speed=0.0))


@pytest.fixture(scope="session")
def truth() -> dict:
    return json.loads((SAMPLES / "ground_truth.json").read_text("utf-8"))


@pytest.fixture(scope="session")
def chat_cases() -> list[dict]:
    return json.loads((SAMPLES / "chat_eval.json").read_text("utf-8"))["cases"]


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog(CONFIG)


@pytest.fixture(scope="session")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Container]:
    """History imported, analytics built, live feed polled up to noon. Shared: read only."""
    built = build_container(
        make_settings(tmp_path_factory.mktemp("seeded") / "data"), source=frozen_source()
    )
    asyncio.run(seed_demo(built))
    yield built
    built.engine.dispose()


@pytest.fixture
def empty(tmp_path: Path) -> Iterator[Container]:
    """An empty database, the demo LLM and the frozen live clock."""
    built = build_container(make_settings(tmp_path / "data"), source=frozen_source())
    yield built
    built.engine.dispose()


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The API, seeded on startup exactly as a fresh clone is."""
    settings = make_settings(tmp_path_factory.mktemp("api") / "data", seed_demo=True)
    with TestClient(create_app(settings, source=frozen_source())) as test_client:
        wait_for(lambda: test_client.get("/api/health").json()["analytics"]["state"] == "ready")
        yield test_client


def wait_for(predicate, timeout: float = 180.0):  # type: ignore[no-untyped-def]
    """Poll until ``predicate()`` returns something truthy (background tasks finishing)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.2)
    raise AssertionError("timed out waiting for background work")
