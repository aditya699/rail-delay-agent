from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.analysis import LiveStatus, UnusualArrival

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/board")
def board(container: ContainerDep) -> list[LiveStatus]:
    """Every train's current state and delay (no forecasts), for the live board."""
    return container.live.board()


@router.get("/unusual")
def unusual(container: ContainerDep) -> list[UnusualArrival]:
    """Today's arrivals that are far later than that train usually is at that stop."""
    return container.live.unusual_today()


@router.post("/poll")
async def poll(container: ContainerDep) -> dict[str, int]:
    """Poll the live source now instead of waiting for the next tick."""
    return {"inserted": await container.live.poll_once()}
