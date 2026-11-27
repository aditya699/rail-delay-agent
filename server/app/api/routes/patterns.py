from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep
from app.schemas.analysis import ModelCard, ReliabilityReport, SeasonalityReport, StationReport

router = APIRouter(prefix="/patterns", tags=["delay patterns"])


@router.get("/hotspots")
def hotspots(
    container: ContainerDep, months: Annotated[list[int] | None, Query()] = None
) -> StationReport:
    """Stations ranked by the delay they add, with 95% cluster-bootstrap intervals."""
    return container.analytics.hotspots([m for m in months or [] if 1 <= m <= 12])


@router.get("/seasonality")
def seasonality(container: ContainerDep) -> SeasonalityReport:
    """Month x station heatmap of added delay, seasonal months and hour-of-day windows."""
    return container.analytics.current.seasonality


@router.get("/reliability")
def reliability(container: ContainerDep) -> ReliabilityReport:
    """Per train, last window: on-time %, mean, median and p90 delay at the destination."""
    return container.analytics.current.reliability.report


@router.get("/model")
def model(container: ContainerDep) -> ModelCard:
    """The forecast's held-out score against the persistence baseline."""
    return container.analytics.current.card


@router.post("/rebuild", status_code=202)
def rebuild(container: ContainerDep) -> dict[str, str]:
    """Re-read analysis.json and rebuild every report and model in the background."""
    container.runner.submit(container.analytics.build(), name="rebuild-analytics")
    return {"state": "building"}
