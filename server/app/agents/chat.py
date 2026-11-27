"""The chatbot: a passenger's message in, a live status, a badge and a cited answer out.

1. **Intent.** The model reads the message (English or Hinglish) and returns a
   :class:`ChatIntent` as structured output: what kind of question, and the train,
   station and months *as written*. It looks nothing up.
2. **Resolve, in code.** The train number must exist in ``network.json``; the station must
   resolve to exactly one code, and be on that train's route. Anything unknown, ambiguous
   or missing becomes a clarifying question with options. The bot never guesses a train.
3. **Tools, in code.** Live status (from ``live_events``), the forecast (p50/p90 to every
   stop ahead), the history badge, or the hotspot ranking. Each returns named facts.
4. **Reply.** The model writes two to five sentences, each citing fact ids. Claims that
   cite unknown ids, or contain a number or time missing from the facts they cite, are
   dropped. If nothing survives, the deterministic template writer answers instead.

The status card and badge in the UI are drawn from the structured result, not the text.
"""

from __future__ import annotations

import html
import json
import logging

from pydantic import BaseModel, Field

from app.agents.citations import check_claims
from app.agents.templates import write_reply
from app.agents.tools import badge_facts, hotspot_facts, status_facts, train_facts
from app.core.catalog import Catalog, Network, Train
from app.llm import load_prompt
from app.llm.base import LLMClient
from app.schemas.analysis import Badge, Fact, LiveStatus, StationStat
from app.schemas.llm import ChatIntent, ChatReply, Claim, IntentKind
from app.services.analytics import AnalyticsService
from app.services.live import LiveService

logger = logging.getLogger(__name__)

TRAIN_KINDS: tuple[IntentKind, ...] = ("train_status", "train_history")


class ChatContext(BaseModel):
    """What the client sends back with the next message, so follow-ups make sense."""

    train_number: str | None = None
    station: str | None = None
    pending: IntentKind | None = Field(
        default=None, description="Set when the bot asked a question; the kind it was answering"
    )


class Option(BaseModel):
    label: str = Field(description="What the button shows")
    value: str = Field(description="What the client sends as the next message when clicked")


class Clarification(BaseModel):
    question: str
    options: list[Option] = Field(default_factory=list)


class ChatResult(BaseModel):
    message: str
    kind: IntentKind
    intent: ChatIntent
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    dropped_claims: list[str] = Field(default_factory=list)
    clarify: Clarification | None = None
    train_number: str | None = None
    station: str | None = None
    status: LiveStatus | None = None
    badge: Badge | None = None
    hotspots: list[StationStat] = Field(default_factory=list)
    hotspot_months: list[int] = Field(default_factory=list)
    facts: dict[str, Fact] = Field(default_factory=dict)
    context: ChatContext
    model: str


class _Clarify(Exception):
    def __init__(self, clarification: Clarification) -> None:
        self.clarification = clarification


def describe_network(network: Network) -> str:
    """The compact list of trains and stations the intent prompt shows the model."""
    trains = "\n".join(
        f"- {t.number} {t.name}: {network.by_code[t.from_].name} -> {network.by_code[t.to].name}"
        for t in network.trains
    )
    stations = "\n".join(
        f"- {s.code} {s.name}" + (f" (also: {', '.join(s.aliases)})" if s.aliases else "")
        for s in network.stations
    )
    shared = "\n".join(
        f"- {name}: {', '.join(codes)}" for name, codes in network.ambiguous_names.items()
    )
    return (
        f"Trains:\n{trains}\n\nStations:\n{stations}\n\nNames shared by several stations:\n{shared}"
    )


def train_option(train: Train, network: Network) -> Option:
    route = f"{network.by_code[train.from_].name} to {network.by_code[train.to].name}"
    return Option(label=f"{train.number} {train.name} ({route})", value=train.number)


def station_option(code: str, network: Network) -> Option:
    name = network.by_code[code].name
    return Option(label=f"{name} ({code})", value=code)


class ChatAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        catalog: Catalog,
        live: LiveService,
        analytics: AnalyticsService,
        intent_effort: str,
        model_label: str,
    ) -> None:
        self.llm = llm
        self.catalog = catalog
        self.network = catalog.network
        self.live = live
        self.analytics = analytics
        self.intent_effort = intent_effort
        self.model_label = model_label
        self.intent_system = load_prompt("intent").replace(
            "{network}", describe_network(self.network)
        )
        self.reply_system = load_prompt("reply")

    async def parse(self, message: str, context: ChatContext) -> ChatIntent:
        content = (
            f"<context>{context.model_dump_json()}</context>\n"
            f"<message>{html.escape(message, quote=False)}</message>"
        )
        return await self.llm.structured(
            system=self.intent_system, content=content, schema=ChatIntent, effort=self.intent_effort
        )

    async def ask(self, message: str, context: ChatContext | None = None) -> ChatResult:
        context = context or ChatContext()
        intent = await self.parse(message, context)
        kind = intent.kind
        if (
            kind == "help"
            and context.pending
            and (intent.train_number or intent.train_name or intent.station)
        ):
            kind = context.pending
        base = {"message": message, "intent": intent, "kind": kind, "model": self.model_label}

        if kind == "help":
            return ChatResult(
                **base,
                answer="I can tell you where a train is and how late it is, when it should reach a "
                "station, how late it usually runs, and which stations lose the most time.",
                clarify=Clarification(
                    question="Try one of these:",
                    options=[Option(label=e, value=e) for e in self.catalog.chat.examples[:4]],
                ),
                context=ChatContext(train_number=context.train_number),
            )
        if kind == "hotspots":
            return await self._hotspots(message, intent, context, base)

        station_text = intent.station or (context.station if context.pending else None)
        try:
            train = self._resolve_train(intent, context)
        except _Clarify as ask:
            # Remember the station they named, so "22448" next is enough.
            codes = self.network.find_stations(station_text)
            remembered = codes[0] if len(codes) == 1 else None
            return self._clarify(
                base, ask.clarification, ChatContext(station=remembered, pending=kind)
            )
        try:
            station = self._resolve_station(station_text, train) if station_text else None
        except _Clarify as ask:
            return self._clarify(
                base, ask.clarification, ChatContext(train_number=train.number, pending=kind)
            )

        facts = train_facts(train, self.network)
        status: LiveStatus | None = None
        if kind == "train_status":
            status = self.live.status(train.number)
            facts += status_facts(status, train, station, self.network)
        badge: Badge | None = None
        if self.analytics.ready:
            analytics = self.analytics.current
            month = intent.months[0] if intent.months else self.live.now().month
            badge = analytics.reliability.badge(train.number, station or train.to, month)
            if badge is not None:
                facts += badge_facts(badge, analytics.config.on_time_minutes)

        result = await self._reply(message, intent, kind, facts, base)
        return result.model_copy(
            update={
                "train_number": train.number,
                "station": station,
                "status": status,
                "badge": badge,
                "context": ChatContext(train_number=train.number, station=station),
            }
        )

    @staticmethod
    def _clarify(base: dict, clarification: Clarification, context: ChatContext) -> ChatResult:
        return ChatResult(
            **base, answer=clarification.question, clarify=clarification, context=context
        )

    async def _hotspots(
        self, message: str, intent: ChatIntent, context: ChatContext, base: dict
    ) -> ChatResult:
        report = self.analytics.hotspots(intent.months)
        top = report.stations[: self.analytics.current.config.hotspot_top_n]
        result = await self._reply(message, intent, "hotspots", hotspot_facts(report), base)
        return result.model_copy(
            update={
                "hotspots": top,
                "hotspot_months": report.months,
                "context": ChatContext(train_number=context.train_number),
            }
        )

    async def _reply(
        self, message: str, intent: ChatIntent, kind: IntentKind, facts: list[Fact], base: dict
    ) -> ChatResult:
        by_id = {f.id: f for f in facts}
        payload = {
            "message": message,
            "language": intent.language,
            "kind": kind,
            "facts": [f.model_dump() for f in facts],
        }
        content = json.dumps(payload, ensure_ascii=False, default=str)
        reply = await self.llm.structured(
            system=self.reply_system, content=content, schema=ChatReply
        )
        kept, dropped = check_claims(reply.claims, by_id)
        if not kept:
            logger.info("No reply claim survived the citation check; using the template writer")
            kept, _ = check_claims(write_reply(payload).claims, by_id)
        cited = {i: by_id[i] for claim in kept for i in claim.fact_ids}
        return ChatResult(
            **base,
            answer=" ".join(c.text for c in kept) or "I have no data for that yet.",
            claims=kept,
            dropped_claims=dropped,
            facts=cited,
            context=ChatContext(),
        )

    # --- Resolution: everything the model said is checked here ---------------------

    def _resolve_train(self, intent: ChatIntent, context: ChatContext) -> Train:
        network = self.network
        if intent.train_number:
            train = network.train(intent.train_number)
            if train is None:
                raise _Clarify(
                    Clarification(
                        question=f"I don't have a train numbered {intent.train_number} in this "
                        "demo "
                        "network. Which one is yours?",
                        options=[train_option(t, network) for t in network.trains[:6]],
                    )
                )
            return train
        if intent.train_name:
            matches = network.find_train_by_name(intent.train_name)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise _Clarify(
                    Clarification(
                        question=f"There is more than one {matches[0].name}. Which direction?",
                        options=[train_option(t, network) for t in matches],
                    )
                )
            raise _Clarify(
                Clarification(
                    question=f"I can't find a train called '{intent.train_name}'. "
                    "Send its 5-digit number.",
                    options=[train_option(t, network) for t in network.trains[:6]],
                )
            )
        if context.train_number and (train := network.train(context.train_number)):
            return train
        raise _Clarify(
            Clarification(
                question="Which train? Send its 5-digit number (or its name).",
                options=[train_option(t, network) for t in network.trains[:4]],
            )
        )

    def _resolve_station(self, text: str, train: Train) -> str:
        network = self.network
        codes = network.find_stations(text)
        stops = [station_option(c, network) for c in train.codes]
        if not codes:
            raise _Clarify(
                Clarification(
                    question=f"I couldn't find a station called '{text}'. Which stop of "
                    f"{train.number} do you mean?",
                    options=stops,
                )
            )
        on_route = [c for c in codes if c in train.codes]
        if len(on_route) == 1:
            return on_route[0]
        if len(on_route) > 1:
            raise _Clarify(
                Clarification(
                    question=f"Which {text}?",
                    options=[station_option(c, network) for c in on_route],
                )
            )
        names = " or ".join(network.by_code[c].name for c in codes)
        raise _Clarify(
            Clarification(
                question=f"{train.number} {train.name} does not stop at {names}. "
                "Which of its stops do you mean?",
                options=stops,
            )
        )
