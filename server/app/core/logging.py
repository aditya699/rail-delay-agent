"""Logging setup. Call :func:`configure_logging` once at startup."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a single readable stream handler."""
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, force=True)
    # The HTTP client libraries are chatty at INFO; keep them quiet unless debugging.
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLogger().level))
