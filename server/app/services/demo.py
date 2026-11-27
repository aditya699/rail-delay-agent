"""First start: load the sample history, build the analytics, take a first live poll."""

from __future__ import annotations

import asyncio
import logging

from app.container import Container

logger = logging.getLogger(__name__)


async def seed_demo(container: Container) -> None:
    """Import ``samples/history.csv.gz`` into an empty database, then build everything."""
    if container.history.count() == 0:
        report = await asyncio.to_thread(
            container.history.seed_samples, container.settings.samples_dir
        )
        logger.info("Seeded %d history rows (%d runs)", report.inserted, report.runs)
    await prepare(container)


async def prepare(container: Container) -> None:
    """Build the analytics (if there is history) and poll the live source once."""
    if container.history.count() and not container.analytics.ready:
        await container.analytics.build()
    inserted = await container.live.poll_once()
    logger.info("First live poll: %d events up to %s", inserted, container.live.last_poll)
