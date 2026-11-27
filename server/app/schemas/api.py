"""Request and response bodies of the HTTP API that are not analysis reports."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.chat import ChatContext
from app.schemas.analysis import Badge, LiveStatus


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: ChatContext | None = None


class TrainStatusOut(BaseModel):
    status: LiveStatus
    badge: Badge | None


class StopOut(BaseModel):
    station: str
    arr: str | None
    dep: str | None


class TrainOut(BaseModel):
    number: str
    name: str
    kind: str
    from_station: str
    to_station: str
    stops: list[StopOut]


class StationOut(BaseModel):
    code: str
    name: str
    lat: float
    lon: float


class CorridorOut(BaseModel):
    id: str
    name: str
    stations: list[str]


class NetworkOut(BaseModel):
    stations: list[StationOut]
    corridors: list[CorridorOut]
    trains: list[TrainOut]
