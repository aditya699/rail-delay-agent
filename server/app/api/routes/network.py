from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.api import CorridorOut, NetworkOut, StationOut, StopOut, TrainOut

router = APIRouter(tags=["network"])


@router.get("/network")
def network(container: ContainerDep) -> NetworkOut:
    """Stations with coordinates, map corridors and every train's timetable."""
    net = container.catalog.network
    return NetworkOut(
        stations=[StationOut(code=s.code, name=s.name, lat=s.lat, lon=s.lon) for s in net.stations],
        corridors=[CorridorOut(id=c.id, name=c.name, stations=c.stations) for c in net.corridors],
        trains=[
            TrainOut(
                number=t.number,
                name=t.name,
                kind=t.kind,
                from_station=t.from_,
                to_station=t.to,
                stops=[StopOut(station=s.station, arr=s.arr, dep=s.dep) for s in t.stops],
            )
            for t in net.trains
        ],
    )
