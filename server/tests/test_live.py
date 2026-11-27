"""The live feed: the clock, the replay source, the poller and the status logic."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.container import Container, build_container
from app.core.errors import NotFoundError
from app.ingest.live import SimClock, SimulatedLiveSource
from tests.conftest import NOON, frozen_source, make_settings


def test_sim_clock_runs_faster_than_real_time() -> None:
    now = [100.0]
    clock = SimClock(datetime(2026, 11, 27, 12, 0), speed=10, monotonic=lambda: now[0])
    now[0] += 60  # one real minute
    assert clock.now() == datetime(2026, 11, 27, 12, 10)
    clock.set(datetime(2026, 11, 27, 18, 0))
    assert clock.now() == datetime(2026, 11, 27, 18, 0)


async def test_replay_only_reports_what_has_happened() -> None:
    source = frozen_source()
    assert source.run_dates[-1].isoformat() == "2026-11-27"
    events = await source.fetch(None, NOON)
    assert events and all(e.actual <= NOON for e in events)
    later = await source.fetch(NOON, NOON + timedelta(hours=1))
    assert all(NOON < e.actual <= NOON + timedelta(hours=1) for e in later)


async def test_polling_twice_stores_each_event_once(empty: Container) -> None:
    first = await empty.live.poll_once()
    assert first > 100
    empty.live.last_poll = None  # as after a restart: fetch everything again
    assert await empty.live.poll_once() == 0
    assert empty.live.event_count() == first


def test_status_of_a_running_train(seeded: Container) -> None:
    status = seeded.live.status("10147")
    assert status.state == "running" and status.run_date.isoformat() == "2026-11-27"
    assert status.last_station is not None and status.delay_min is not None
    assert status.forecasts and status.forecasts[0].station == status.next_station
    # It has not reached the next stop yet, so the forecast cannot put it there before now.
    assert status.forecasts[0].eta_p50 > NOON
    assert all(f.eta_p90 >= f.eta_p50 for f in status.forecasts)


def test_status_of_a_train_that_has_not_left(seeded: Container) -> None:
    status = seeded.live.status("22974")  # leaves Vadodara at 15:45
    assert status.state == "not_started"
    assert status.scheduled_departure == datetime(2026, 11, 27, 15, 45)
    assert status.forecasts == []


def test_overnight_train_is_found_on_yesterdays_run(seeded: Container) -> None:
    status = seeded.live.status("22958")  # left New Delhi 16:45 yesterday, due Mumbai 14:00
    assert status.state == "running" and status.run_date.isoformat() == "2026-11-26"


async def test_a_finished_run_shows_as_arrived(tmp_path: Path) -> None:
    source = frozen_source()
    final = max(
        (e for e in source.events if e.train_no == "16572" and e.event == "arr"),
        key=lambda e: e.seq,
    )
    source.clock.set(final.actual + timedelta(minutes=30))
    container = build_container(make_settings(tmp_path / "data"), source=source)
    await container.live.poll_once()
    status = container.live.status("16572")
    assert status.state == "arrived" and status.last_station == "CSMT"
    assert status.delay_min == final.delay_min
    container.engine.dispose()


def test_unknown_train(seeded: Container) -> None:
    with pytest.raises(NotFoundError):
        seeded.live.status("99999")


def test_board_lists_every_train(seeded: Container) -> None:
    board = seeded.live.board()
    assert len(board) == len(seeded.catalog.network.trains)
    assert {s.state for s in board} >= {"running", "not_started"}


async def test_the_planted_incident_is_flagged_unusual(seeded: Container, truth: dict) -> None:
    source = seeded.live.source
    assert isinstance(source, SimulatedLiveSource)
    await seeded.live.poll_once(until=datetime(2026, 11, 29))
    flagged = seeded.live.unusual_today(clock=datetime(2026, 11, 28))
    incident = truth["unusual_today"][0]
    keys = {(u.train_no, u.station) for u in flagged}
    assert (incident["train"], incident["station"]) in keys
    assert len(keys) <= 3
    hit = next(u for u in flagged if u.train_no == incident["train"])
    assert hit.delay_min > hit.usual_p90 + 15
