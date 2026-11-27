"""A deterministic stand-in for Claude.

Used two ways:

* **Tests** pass their own ``responders`` so every LLM answer is scripted.
* **Demo mode** (``LLM_PROVIDER=fake``) uses :func:`build_demo_llm`: the intent step is
  keyword rules (:mod:`app.llm.fake_parser`) reading the same ``<context>`` and
  ``<message>`` the real prompt sends, and the reply is the template writer
  (:mod:`app.agents.templates`) reading the same facts. Every number still comes from the
  analysis, so the UI, the citation check and the eval behave the same without a key.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.agents.templates import write_reply
from app.core.catalog import Catalog
from app.llm.base import Content, T
from app.llm.fake_parser import parse_message
from app.schemas.llm import ChatIntent, ChatReply

Responder = Callable[[str, Content], BaseModel]


class FakeLLM:
    """An :class:`~app.llm.base.LLMClient` whose answers come from Python callables."""

    def __init__(self, responders: dict[type[BaseModel], Responder] | None = None) -> None:
        self.responders = responders or {}
        self.calls: list[tuple[str, Any]] = []

    async def structured(
        self,
        *,
        system: str,
        content: Content,
        schema: type[T],
        effort: str | None = None,
    ) -> T:
        self.calls.append((schema.__name__, content))
        responder = self.responders.get(schema)
        if responder is None:
            raise AssertionError(f"FakeLLM has no responder for {schema.__name__}")
        result = responder(system, content)
        if not isinstance(result, schema):
            raise AssertionError(f"Responder for {schema.__name__} returned {type(result)}")
        return result


def _tag(content: Content, name: str) -> str:
    text = content if isinstance(content, str) else json.dumps(content)
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return match.group(1).strip() if match else ""


def build_demo_llm(catalog: Catalog) -> FakeLLM:
    def intent(_: str, content: Content) -> ChatIntent:
        context = json.loads(_tag(content, "context") or "{}")
        message = html.unescape(_tag(content, "message"))
        return parse_message(message, catalog.network, context.get("pending"))

    def reply(_: str, content: Content) -> ChatReply:
        payload = json.loads(content if isinstance(content, str) else json.dumps(content))
        return write_reply(payload)

    return FakeLLM(responders={ChatIntent: intent, ChatReply: reply})
