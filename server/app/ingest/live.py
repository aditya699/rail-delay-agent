"""Live train-running sources: where arrival and departure events come from.

Every source implements :class:`LiveSource`: a clock and ``fetch(since, until)``, returning
the arrivals and departures that happened in that window. The poller
(:class:`app.services.live.LiveService`) stores them in ``live_events``; nothing else in the
app knows which source is behind it.

* :class:`SimulatedLiveSource` (the default) replays ``samples/live_replay.csv``, two days
  held out of the history, on an accelerated clock. Same network, same planted patterns,
  so the forecast and the "unusual today" flag can be checked against what really happens.
* :class:`RunningStatusApiSource` is a **stub** for a third-party running-status API, off
  by default and not tested against any real service. Read docs/data-sources.md first:
  Indian Railways publishes no official public API for this, and NTES/IRCTC pages must not
  be scraped.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel

from app.analysis.dataset import read_history_csv
from app.core.catalog import Network

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class FeedEvent(BaseModel):
    """One arrival or departure of one run, as a feed reports it."""

    train_no: str
    run_date: date
    seq: int
    station: str
    event: Literal["arr", "dep"]
    scheduled: datetime
    actual: datetime

    @property
    def delay_min(self) -> int:
        return int(round((self.actual - self.scheduled).total_seconds() / 60))


class LiveSource(Protocol):
    name: str

    def now(self) -> datetime:
        """The source's current time (IST, naive). The simulated source runs its own clock."""
        ...

    async def fetch(self, since: datetime | None, until: datetime) -> list[FeedEvent]:
        """Events with ``since < actual <= until`` (``since=None``: everything so far)."""
        ...


class SimClock:
    """A clock that starts at ``start`` and runs ``speed`` times faster than real time."""

    def __init__(
        self, start: datetime, speed: float = 1.0, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self._monotonic = monotonic
        self.speed = speed
        self.set(start)

    def set(self, when: datetime) -> None:
        self._start = when
        self._t0 = self._monotonic()

    def now(self) -> datetime:
        elapsed = (self._monotonic() - self._t0) * self.speed
        return (self._start + timedelta(seconds=elapsed)).replace(microsecond=0)


def events_from_rows(frame: Any) -> list[FeedEvent]:
    """Arrival and departure events from a frame in the history CSV's shape."""
    events: list[FeedEvent] = []
    for row in frame.itertuples(index=False):
        for kind, sched, actual in (
            ("arr", row.sched_arr, row.act_arr),
            ("dep", row.sched_dep, row.act_dep),
        ):
            if sched is None or actual is None or sched != sched or actual != actual:  # NaT
                continue
            events.append(
                FeedEvent(
                    train_no=str(row.train_no),
                    run_date=row.run_date.date(),
                    seq=int(row.seq),
                    station=str(row.station),
                    event=kind,  # type: ignore[arg-type]
                    scheduled=sched.to_pydatetime(),
                    actual=actual.to_pydatetime(),
                )
            )
    events.sort(key=lambda e: (e.actual, e.train_no, e.seq, e.event))
    return events


class SimulatedLiveSource:
    """Replay held-out runs as if a feed reported each event when it happened."""

    name = "simulated"

    def __init__(self, replay_path: Path, clock: SimClock) -> None:
        self.clock = clock
        self.path = replay_path
        self.events = events_from_rows(read_history_csv(replay_path))
        self.run_dates = sorted({e.run_date for e in self.events})

    def now(self) -> datetime:
        return self.clock.now()

    async def fetch(self, since: datetime | None, until: datetime) -> list[FeedEvent]:
        return [e for e in self.events if (since is None or e.actual > since) and e.actual <= until]


class RunningStatusApiSource:
    """Stub adapter for a third-party running-status API. **Unverified.**

    Expects, for ``GET {base_url}/trains/{number}/runs/{YYYY-MM-DD}`` with
    ``Authorization: Bearer {api_key}``, a JSON body like::

        {"stops": [{"seq": 0, "station": "NDLS", "sched_dep": "2026-11-27T16:55:00",
                    "act_dep": "2026-11-27T17:02:00"}, ...]}

    Real providers all differ: adapt :meth:`_parse` to yours, keep the request rate low,
    and follow the provider's terms. It polls today's and yesterday's run of every train in
    ``network.json`` (yesterday's, because overnight trains are still running).
    """

    name = "http"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        network: Network,
        timeout: float = 10.0,
        user_agent: str = "rail-delay-agent/0.1",
    ) -> None:
        headers = {"User-Agent": user_agent}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
        )
        self._network = network

    def now(self) -> datetime:
        return datetime.now(IST).replace(tzinfo=None, microsecond=0)

    async def fetch(self, since: datetime | None, until: datetime) -> list[FeedEvent]:
        events: list[FeedEvent] = []
        today = until.date()
        for train in self._network.trains:
            for run_date in (today - timedelta(days=1), today):
                try:
                    response = await self._client.get(
                        f"/trains/{train.number}/runs/{run_date.isoformat()}"
                    )
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    events += self._parse(train.number, run_date, response.json())
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    logger.warning("Running-status API: %s on %s: %s", train.number, run_date, exc)
        return [e for e in events if (since is None or e.actual > since) and e.actual <= until]

    @staticmethod
    def _parse(train_no: str, run_date: date, body: dict[str, Any]) -> list[FeedEvent]:
        out = []
        for stop in body.get("stops", []):
            for kind in ("arr", "dep"):
                sched, actual = stop.get(f"sched_{kind}"), stop.get(f"act_{kind}")
                if sched and actual:
                    out.append(
                        FeedEvent(
                            train_no=train_no,
                            run_date=run_date,
                            seq=int(stop["seq"]),
                            station=str(stop["station"]),
                            event=kind,  # type: ignore[arg-type]
                            scheduled=datetime.fromisoformat(sched).replace(tzinfo=None),
                            actual=datetime.fromisoformat(actual).replace(tzinfo=None),
                        )
                    )
        return out

    async def aclose(self) -> None:
        await self._client.aclose()
