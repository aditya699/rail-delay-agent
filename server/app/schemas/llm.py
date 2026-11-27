"""Structured outputs: the shapes the language model must answer in.

The model does two small jobs and nothing else:

1. :class:`ChatIntent`: read the passenger's message (English or Hinglish) and say what
   they asked about. It does not look anything up and does not resolve codes; the
   application validates every field against ``network.json``.
2. :class:`ChatReply`: phrase an answer from computed facts, citing their ids.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IntentKind = Literal["train_status", "train_history", "hotspots", "help"]


class ChatIntent(BaseModel):
    kind: IntentKind = Field(
        description=(
            "train_status: where is a train now / is it late / when will it reach a station. "
            "train_history: how late a train usually is. "
            "hotspots: which stations or routes lose the most time. "
            "help: anything else."
        )
    )
    train_number: str | None = Field(
        default=None, description="The train number exactly as the user wrote it, digits only."
    )
    train_name: str | None = Field(
        default=None, description="A train name the user wrote instead of a number, as written."
    )
    station: str | None = Field(
        default=None,
        description="The station the user asked about, as written (name, code or old name).",
    )
    months: list[int] = Field(
        default_factory=list,
        description="Months (1-12) the question is about; winter/fog = [12, 1], "
        "monsoon/rain = [7, 8]; empty if none.",
    )
    language: Literal["english", "hinglish"] = Field(
        default="english", description="hinglish if the user wrote Hindi in Latin script."
    )


class Claim(BaseModel):
    text: str = Field(description="One short sentence for a passenger.")
    fact_ids: list[str] = Field(description="Ids of the facts this sentence relies on.")


class ChatReply(BaseModel):
    claims: list[Claim] = Field(description="Two to five sentences, most important first.")
