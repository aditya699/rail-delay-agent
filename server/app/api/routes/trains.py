from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.api import TrainStatusOut

router = APIRouter(prefix="/trains", tags=["trains"])


@router.get("/{number}/status")
def train_status(number: str, container: ContainerDep) -> TrainStatusOut:
    """Live status with forecasts to every stop ahead, and the badge for its destination."""
    status = container.live.status(number)
    badge = None
    if container.analytics.ready:
        train = container.live.train(number)
        badge = container.analytics.current.reliability.badge(
            train.number, train.to, container.live.now().month
        )
    return TrainStatusOut(status=status, badge=badge)
