"""What each analysis returns. These are the API's payloads and the chatbot's evidence.

Every report carries ``facts``: flat, named numbers. The chat reply may only cite fact
ids, and claims citing ids that do not exist (or numbers that are not in the facts they
cite) are dropped, so an answer can never contain a number the analysis did not compute.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Fact(BaseModel):
    id: str
    label: str
    value: float | int | str | bool
    unit: str = ""


def fact(id: str, label: str, value: float | int | str | bool, unit: str = "") -> Fact:
    """A fact, with floats rounded to one decimal (minutes and percentages)."""
    if isinstance(value, float):
        value = round(value, 1)
    return Fact(id=id, label=label, value=value, unit=unit)


# --- Stations: added vs inherited ---------------------------------------------------


class StationStat(BaseModel):
    code: str
    name: str
    n: int = Field(description="Arrivals observed")
    arrival_mean: float = Field(description="Mean arrival delay: what a passenger sees")
    inherited_mean: float = Field(
        description="Mean delay the train already had leaving the stop before"
    )
    added_mean: float = Field(description="Mean delay gained on the approach to this station")
    added_ci_low: float
    added_ci_high: float
    added_p90: float
    added_share: float | None = Field(description="added / arrival, when the train arrives late")
    rank: int


class StationReport(BaseModel):
    months: list[int] = Field(description="Months the rows were filtered to; empty = all year")
    stations: list[StationStat] = Field(description="Sorted by added delay, worst first")
    naive_top: str = Field(description="The station with the worst mean arrival delay")
    facts: list[Fact] = Field(default_factory=list)


# --- Seasonality and hour of day ----------------------------------------------------


class HeatCell(BaseModel):
    station: str
    month: int
    n: int
    added_mean: float


class SeasonalStation(BaseModel):
    station: str
    baseline: float = Field(description="Median of the station's monthly mean added delay")
    months: list[int] = Field(description="Months well above the baseline")
    peak_month: int
    peak_added: float


class HourCell(BaseModel):
    station: str
    hour: int
    n: int
    added_mean: float


class HourWindow(BaseModel):
    station: str
    hours: list[int]
    label: str
    excess: float = Field(
        description="Mean added delay in the window minus the station's median hour"
    )


class SeasonalityReport(BaseModel):
    cells: list[HeatCell]
    seasonal: list[SeasonalStation]
    hours: list[HourCell]
    windows: list[HourWindow]
    facts: list[Fact] = Field(default_factory=list)


# --- Reliability (the badge) --------------------------------------------------------


class DelayStats(BaseModel):
    n: int
    mean: float
    median: float
    p90: float
    on_time_pct: float


class TrainReliability(BaseModel):
    number: str
    name: str
    from_station: str
    to_station: str
    destination: DelayStats | None
    label: Literal["chronically_late", "reliable"] | None = None


class ReliabilityReport(BaseModel):
    as_of: date
    window_start: date
    window_days: int
    on_time_minutes: int
    trains: list[TrainReliability]
    most_late: str
    most_on_time: str
    facts: list[Fact] = Field(default_factory=list)


class Badge(BaseModel):
    """The 'based on previous patterns' badge shown under a live status."""

    train_no: str
    station: str
    station_name: str
    window_days: int
    n: int
    mean: float
    median: float
    p90: float
    on_time_pct: float
    month: int | None = None
    month_mean: float | None = None
    month_n: int | None = None


# --- Forecast -----------------------------------------------------------------------


class HorizonScore(BaseModel):
    bucket: str
    n: int
    mae_model: float
    mae_persistence: float


class ModelCard(BaseModel):
    trained_on: str
    test_start: date
    test_end: date
    n_train: int
    n_test: int
    features: list[str]
    mae_model: float
    mae_persistence: float
    mae_improvement_pct: float
    p90_coverage: float
    by_horizon: list[HorizonScore]
    facts: list[Fact] = Field(default_factory=list)


class StopForecast(BaseModel):
    seq: int
    station: str
    station_name: str
    sched_arr: datetime
    p50_delay: int
    p90_delay: int
    eta_p50: datetime
    eta_p90: datetime


# --- Live status --------------------------------------------------------------------


class LiveStatus(BaseModel):
    train_no: str
    name: str
    from_station: str
    to_station: str
    run_date: date
    state: Literal["not_started", "running", "arrived"]
    clock: datetime = Field(description="The live source's clock when this was computed")
    last_station: str | None = None
    last_station_name: str | None = None
    last_event: Literal["arr", "dep"] | None = None
    last_event_at: datetime | None = None
    delay_min: int | None = None
    scheduled_departure: datetime | None = None
    next_station: str | None = None
    forecasts: list[StopForecast] = Field(default_factory=list)
    unusual: bool = False
    usual_median: float | None = None
    usual_p90: float | None = None
    source: str


class UnusualArrival(BaseModel):
    """An arrival today that is far later than this train usually is at this stop."""

    train_no: str
    name: str
    run_date: date
    station: str
    station_name: str
    arrived_at: datetime
    delay_min: int
    usual_median: float
    usual_p90: float
