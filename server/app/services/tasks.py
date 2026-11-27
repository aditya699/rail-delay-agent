"""A tiny in-process background task runner.

Good enough for a single server process. For multiple workers or durable jobs,
swap it for a real queue (Celery, RQ, Arq, Dramatiq); the pipeline only needs
``submit``. See docs/extending.md.

FastAPI runs plain ``def`` endpoints in a thread pool, where there is no running
event loop, so the runner is bound to the server's loop at startup and hands
work over to it thread-safely.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TaskRunner:
    """Run fire-and-forget coroutines on one event loop, from any thread."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the runner to the loop that will execute tasks (the server's loop)."""
        self._loop = loop

    def submit(self, coroutine: Coroutine[Any, Any, Any], name: str) -> None:
        """Schedule ``coroutine``; safe to call from the loop or from a worker thread."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        loop = self._loop or running
        if loop is None:
            coroutine.close()
            raise RuntimeError("TaskRunner.bind() was not called and no event loop is running")
        if running is loop:
            self._start(coroutine, name)
        else:
            loop.call_soon_threadsafe(self._start, coroutine, name)

    def _start(self, coroutine: Coroutine[Any, Any, Any], name: str) -> None:
        task = asyncio.get_running_loop().create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Task %s crashed", task.get_name(), exc_info=task.exception())

    @property
    def pending(self) -> int:
        """Number of tasks still running."""
        return len(self._tasks)

    async def shutdown(self) -> None:
        """Cancel whatever is still running (called on app shutdown)."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
