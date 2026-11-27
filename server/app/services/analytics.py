"""Build every analysis from the history once, keep it in memory, serve it.

Building takes a few seconds (two quantile models are fitted twice: once to score them on
held-out days, once on all history to serve), so it runs in a worker thread and the API
answers with ``503 not_ready`` until it is done. ``/api/health`` shows the state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd
from sqlalchemy import Engine

from app.analysis.dataset import load_history, prepare
from app.analysis.predict import DelayForecaster
from app.analysis.reliability import ReliabilityIndex, reliability
from app.analysis.seasonality import seasonality
from app.analysis.stations import station_profile
from app.core.catalog import AnalysisConfig, Catalog
from app.core.errors import ConflictError, NotReadyError
from app.schemas.analysis import ModelCard, SeasonalityReport, StationReport

logger = logging.getLogger(__name__)

State = Literal["empty", "building", "ready", "failed"]


@dataclass
class Analytics:
    config: AnalysisConfig
    stops: pd.DataFrame
    as_of: date
    stations: StationReport
    seasonality: SeasonalityReport
    reliability: ReliabilityIndex
    forecaster: DelayForecaster
    card: ModelCard
    seconds: float
    _hotspots: dict[tuple[int, ...], StationReport] = field(default_factory=dict)


class AnalyticsService:
    def __init__(self, engine: Engine, catalog: Catalog) -> None:
        self.engine = engine
        self.catalog = catalog
        self.state: State = "empty"
        self.error: str | None = None
        self._current: Analytics | None = None
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._current is not None

    @property
    def current(self) -> Analytics:
        if self._current is None:
            raise NotReadyError(
                "The delay models are still being built from the history; try again in a few "
                "seconds."
                if self.state == "building"
                else f"Analytics are {self.state}."
            )
        return self._current

    async def build(self) -> Analytics:
        if self._lock.locked():
            raise ConflictError("The analytics are already being rebuilt.")
        async with self._lock:
            self.state, self.error = "building", None
            try:
                result = await asyncio.to_thread(self.build_sync)
            except Exception as exc:
                self.state, self.error = "failed", str(exc)
                logger.exception("Analytics build failed")
                raise
            return result

    def build_sync(self) -> Analytics:
        """Load history, then compute every report and fit the forecaster."""
        started = time.monotonic()
        self.state = "building"
        config = self.catalog.reload_analysis()
        network = self.catalog.network
        raw = load_history(self.engine)
        if raw.empty:
            raise NotReadyError("There is no history to learn from; import some first.")
        stops = prepare(raw, network)
        forecaster = DelayForecaster(network, config)
        card = forecaster.fit(stops)
        analytics = Analytics(
            config=config,
            stops=stops,
            as_of=stops["run_date"].max().date(),
            stations=station_profile(stops, network, config),
            seasonality=seasonality(stops, config),
            reliability=reliability(stops, network, config),
            forecaster=forecaster,
            card=card,
            seconds=round(time.monotonic() - started, 1),
        )
        self._current = analytics
        self.state = "ready"
        logger.info("Analytics ready in %.1fs (%d stops)", analytics.seconds, len(stops))
        return analytics

    def hotspots(self, months: list[int] | None = None) -> StationReport:
        """The station ranking, for all year or some months (cached per month set)."""
        analytics = self.current
        key = tuple(sorted(set(months or [])))
        if not key:
            return analytics.stations
        if key not in analytics._hotspots:
            analytics._hotspots[key] = station_profile(
                analytics.stops, self.catalog.network, analytics.config, months=list(key)
            )
        return analytics._hotspots[key]
