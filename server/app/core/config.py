"""Application settings, loaded from environment variables and ``server/.env``.

Every tunable lives here so the rest of the code never reads ``os.environ`` directly.
See ``server/.env.example`` for a documented list of variables. Editorial choices (the
network of stations and trains, analysis thresholds, example questions) are data files in
``app/config/``, not settings.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[2]
"""Absolute path of the ``server/`` folder, so relative paths work from any cwd."""

REPO_DIR = SERVER_DIR.parent

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    """Typed configuration for the whole backend."""

    model_config = SettingsConfigDict(
        env_file=SERVER_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -----------------------------------------------------------------
    app_name: str = "Rail Delay Agent"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_demo: bool = True

    # --- Storage -------------------------------------------------------------
    data_dir: Path = SERVER_DIR / "data"
    database_url: str | None = None

    # --- LLM -----------------------------------------------------------------
    llm_provider: Literal["anthropic", "fake"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Effort = "medium"
    intent_effort: Effort = "low"
    max_concurrency: int = 4

    # --- Live feed -----------------------------------------------------------
    live_source: Literal["simulated", "http"] = "simulated"
    live_poll_seconds: float = 5.0
    # Simulated feed only: where its clock starts and how fast it runs.
    live_start: datetime = datetime(2026, 11, 27, 12, 0)
    live_speed: float = 10.0
    # Third-party running-status API (LIVE_SOURCE=http). Unverified; see docs/data-sources.md.
    running_status_api_url: str | None = None
    running_status_api_key: SecretStr | None = None
    running_status_timeout: float = 10.0
    http_user_agent: str = "rail-delay-agent/0.1 (+https://github.com/aditya699/rail-delay-agent)"

    # --- Data-driven config --------------------------------------------------
    config_dir: Path = SERVER_DIR / "app" / "config"
    samples_dir: Path = REPO_DIR / "samples"

    @field_validator("data_dir", "config_dir", "samples_dir", mode="after")
    @classmethod
    def _resolve_relative(cls, value: Path) -> Path:
        """Interpret relative paths as relative to ``server/``, not the current directory."""
        return value if value.is_absolute() else (SERVER_DIR / value).resolve()

    @property
    def sqlalchemy_url(self) -> str:
        """Database URL, defaulting to a SQLite file inside ``data_dir``."""
        return self.database_url or f"sqlite:///{(self.data_dir / 'rail.db').as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        """``CORS_ORIGINS`` split on commas."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def model_label(self) -> str:
        """What the UI shows as the model: the Claude model id, or ``demo``."""
        return self.anthropic_model if self.llm_provider == "anthropic" else "demo"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests build their own)."""
    return Settings()
