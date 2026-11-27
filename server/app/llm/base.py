"""The interface every language-model backend implements.

The chatbot depends on :class:`LLMClient`, never on a vendor SDK, so you can swap the
provider (or use :class:`app.llm.fake.FakeLLM` in tests) without touching it.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

Content = str | list[dict[str, Any]]
"""A user message: plain text, or a list of content blocks."""


class LLMClient(Protocol):
    """Minimal surface the app needs from a language model."""

    async def structured(
        self,
        *,
        system: str,
        content: Content,
        schema: type[T],
        effort: str | None = None,
    ) -> T:
        """Return the model's answer parsed into ``schema`` (a Pydantic model).

        ``effort`` overrides the client's default effort for this one call.
        """
        ...
