"""Language-model layer: an interface, a Claude implementation and a fake."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.llm.base import LLMClient

if TYPE_CHECKING:
    from app.core.catalog import Catalog

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    """Read ``app/llm/prompts/<name>.md``."""
    return (PROMPTS_DIR / f"{name}.md").read_text("utf-8").strip()


def build_llm(settings: Settings, catalog: Catalog) -> LLMClient:
    """Return the LLM client selected by ``LLM_PROVIDER``."""
    if settings.llm_provider == "fake":
        from app.llm.fake import build_demo_llm

        return build_demo_llm(catalog)

    from app.llm.anthropic_client import AnthropicLLM

    api_key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    return AnthropicLLM(
        model=settings.anthropic_model,
        effort=settings.anthropic_effort,
        api_key=api_key or None,
        max_concurrency=settings.max_concurrency,
    )
