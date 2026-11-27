from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ContainerDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(container: ContainerDep) -> dict[str, Any]:
    """Liveness plus the switches and progress the UI shows."""
    settings = container.settings
    analytics = container.analytics
    live = container.live
    current = analytics.current if analytics.ready else None
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "model": settings.model_label,
        "history_rows": container.history.count(),
        "analytics": {
            "state": analytics.state,
            "error": analytics.error,
            "seconds": current.seconds if current else None,
            "as_of": current.as_of.isoformat() if current else None,
        },
        "live": {
            "source": live.source.name,
            "clock": live.now().isoformat(),
            "speed": settings.live_speed if live.source.name == "simulated" else 1.0,
            "poll_seconds": live.poll_seconds,
            "last_poll": live.last_poll.isoformat() if live.last_poll else None,
            "events": live.event_count(),
        },
        "background_tasks": container.runner.pending,
    }
