from __future__ import annotations

from fastapi import APIRouter

from app.agents.chat import ChatResult
from app.api.deps import ContainerDep
from app.schemas.api import ChatIn

router = APIRouter(prefix="/chat", tags=["chatbot"])


@router.get("/examples")
def chat_examples(container: ContainerDep) -> list[str]:
    return container.catalog.chat.examples


@router.post("")
async def ask(body: ChatIn, container: ContainerDep) -> ChatResult:
    """A message in; a clarifying question, or a live status, badge and cited answer out.

    Send the returned ``context`` back with the next message so follow-ups (a bare train
    number after "Which train?") are understood.
    """
    return await container.chat.ask(body.message.strip(), body.context)
