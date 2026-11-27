"""The live side: poll the source, store events, answer "where is train X now?".

The poller runs inside the API process every ``LIVE_POLL_SECONDS`` (0 = off). For several
API workers, switch it off there and run ``python -m app.cli ingest --watch`` as one
separate process instead, so only one writer polls the source (see docs/architecture.md).
Events are deduplicated on (train, run date, stop, arr/dep), so re-polling is harmless.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.predict import scheduled_times
from app.analysis.unusual import is_unusual
from app.core.catalog import Network, Train
from app.core.errors import NotFoundError
from app.db.models import LiveEvent
from app.db.session import session_scope
from app.ingest.live import FeedEvent, LiveSource
from app.schemas.analysis import LiveStatus, UnusualArrival
from app.services.analytics import AnalyticsService

logger = logging.getLogger(__name__)

ARRIVED_SHOWN_FOR = timedelta(hours=3)
"""A finished run stays the answer for this long before the next run takes over."""


class LiveService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        source: LiveSource,
        network: Network,
        analytics: AnalyticsService,
        poll_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.source = source
        self.network = network
        self.analytics = analytics
        self.poll_seconds = poll_seconds
        self.last_poll: datetime | None = None
        self.last_inserted = 0
        self._task: asyncio.Task[None] | None = None

    # --- Ingestion ------------------------------------------------------------------

    def now(self) -> datetime:
        return self.source.now()

    async def poll_once(self, until: datetime | None = None) -> int:
        """Fetch events up to ``until`` (default: the source's now) and store new ones."""
        until = until or self.source.now()
        events = await self.source.fetch(self.last_poll, until)
        inserted = self.store(events)
        self.last_poll = until
        self.last_inserted = inserted
        return inserted

    def store(self, events: list[FeedEvent]) -> int:
        if not events:
            return 0
        with session_scope(self.session_factory) as session:
            keys = {(e.train_no, e.run_date) for e in events}
            existing = set(
                session.execute(
                    select(
                        LiveEvent.train_no, LiveEvent.run_date, LiveEvent.seq, LiveEvent.event
                    ).where(tuple_(LiveEvent.train_no, LiveEvent.run_date).in_(list(keys)))
                ).all()
            )
            fresh = [e for e in events if (e.train_no, e.run_date, e.seq, e.event) not in existing]
            for e in fresh:
                session.add(
                    LiveEvent(
                        train_no=e.train_no,
                        run_date=e.run_date,
                        seq=e.seq,
                        station=e.station,
                        event=e.event,
                        scheduled=e.scheduled,
                        actual=e.actual,
                        delay_min=e.delay_min,
                        source=self.source.name,
                    )
                )
        return len(fresh)

    def start(self) -> None:
        if self.poll_seconds > 0 and self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._loop(), name="live-poller")
            logger.info(
                "Live poller: every %.0fs from the %s source", self.poll_seconds, self.source.name
            )

    async def _loop(self) -> None:
        while True:
            try:
                inserted = await self.poll_once()
                if inserted:
                    logger.info("Live poller stored %d events (clock %s)", inserted, self.last_poll)
            except Exception:
                logger.exception("Live poll failed")
            await asyncio.sleep(self.poll_seconds)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        close = getattr(self.source, "aclose", None)
        if close is not None:
            await close()

    def event_count(self) -> int:
        with session_scope(self.session_factory) as session:
            return len(session.scalars(select(LiveEvent.id)).all())

    # --- Status ---------------------------------------------------------------------

    def train(self, number: str) -> Train:
        train = self.network.train(number)
        if train is None:
            raise NotFoundError(f"Train {number} is not in this network.")
        return train

    def status(self, number: str, *, with_forecast: bool = True) -> LiveStatus:
        train = self.train(number)
        clock = self.source.now()
        today = clock.date()
        with session_scope(self.session_factory) as session:
            rows = session.scalars(
                select(LiveEvent)
                .where(
                    LiveEvent.train_no == train.number,
                    LiveEvent.run_date.in_([today - timedelta(days=1), today]),
                    LiveEvent.actual <= clock,
                )
                .order_by(LiveEvent.actual, LiveEvent.seq)
            ).all()
        by_run: dict[date, list[LiveEvent]] = {}
        for row in rows:
            by_run.setdefault(row.run_date, []).append(row)
        final = len(train.stops) - 1

        def finished(events: list[LiveEvent]) -> bool:
            return any(e.seq == final and e.event == "arr" for e in events)

        running = [d for d, ev in by_run.items() if not finished(ev)]
        recent = [
            d
            for d, ev in by_run.items()
            if finished(ev) and clock - ev[-1].actual <= ARRIVED_SHOWN_FOR
        ]
        if running:
            run_date = max(running)
        elif recent:
            run_date = max(recent)
        else:
            return self._not_started(train, today, clock)

        events = by_run[run_date]
        last = events[-1]
        status = LiveStatus(
            train_no=train.number,
            name=train.name,
            from_station=train.from_,
            to_station=train.to,
            run_date=run_date,
            state="arrived" if finished(events) else "running",
            clock=clock,
            last_station=last.station,
            last_station_name=self.network.by_code[last.station].name,
            last_event=last.event,  # type: ignore[arg-type]
            last_event_at=last.actual,
            delay_min=last.delay_min,
            next_station=train.stops[last.seq + 1].station if last.seq < final else None,
            source=self.source.name,
        )
        if self.analytics.ready:
            analytics = self.analytics.current
            usual = analytics.reliability.by_stop.get((train.number, last.station))
            if usual is not None and last.seq > 0:
                status.usual_median = usual.median
                status.usual_p90 = usual.p90
                status.unusual = is_unusual(last.delay_min, usual, analytics.config.unusual)
            if with_forecast and status.state == "running":
                current = max(last.delay_min, 0)
                forecasts = analytics.forecaster.forecast(train, run_date, last.seq, current)
                for item in forecasts:
                    # It has not arrived anywhere ahead yet, so it cannot arrive before now.
                    floor = int((clock - item.sched_arr).total_seconds() // 60) + 1
                    if item.p50_delay < floor:
                        item.p50_delay = floor
                        item.eta_p50 = item.sched_arr + timedelta(minutes=floor)
                    if item.p90_delay < item.p50_delay:
                        item.p90_delay = item.p50_delay
                        item.eta_p90 = item.eta_p50
                status.forecasts = forecasts
        return status

    def _not_started(self, train: Train, today: date, clock: datetime) -> LiveStatus:
        departure = scheduled_times(train, today)[0][1]
        return LiveStatus(
            train_no=train.number,
            name=train.name,
            from_station=train.from_,
            to_station=train.to,
            run_date=today,
            state="not_started",
            clock=clock,
            scheduled_departure=departure,
            next_station=train.from_,
            source=self.source.name,
        )

    def board(self) -> list[LiveStatus]:
        """Every train's current status, without forecasts (for the live board)."""
        return [self.status(t.number, with_forecast=False) for t in self.network.trains]

    def unusual_today(self, clock: datetime | None = None) -> list[UnusualArrival]:
        """Arrivals on the current (and previous) run date far later than this train's usual."""
        if not self.analytics.ready:
            return []
        analytics = self.analytics.current
        clock = clock or self.source.now()
        with session_scope(self.session_factory) as session:
            rows = session.scalars(
                select(LiveEvent)
                .where(
                    LiveEvent.event == "arr",
                    LiveEvent.seq > 0,
                    LiveEvent.run_date.in_([clock.date() - timedelta(days=1), clock.date()]),
                    LiveEvent.actual <= clock,
                )
                .order_by(LiveEvent.actual)
            ).all()
        out = []
        for row in rows:
            usual = analytics.reliability.by_stop.get((row.train_no, row.station))
            if usual is None or not is_unusual(row.delay_min, usual, analytics.config.unusual):
                continue
            out.append(
                UnusualArrival(
                    train_no=row.train_no,
                    name=self.network.by_number[row.train_no].name,
                    run_date=row.run_date,
                    station=row.station,
                    station_name=self.network.by_code[row.station].name,
                    arrived_at=row.actual,
                    delay_min=row.delay_min,
                    usual_median=usual.median,
                    usual_p90=usual.p90,
                )
            )
        return out
