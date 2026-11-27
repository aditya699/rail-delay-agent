"""The chatbot: intent (never a guessed train), resolution, tools, cited reply."""

from __future__ import annotations

import pytest

from app.agents.chat import ChatAgent, ChatContext
from app.agents.citations import check_claims, numbers_in
from app.container import Container
from app.core.catalog import Catalog
from app.llm.fake import FakeLLM, build_demo_llm
from app.llm.fake_parser import parse_message
from app.schemas.analysis import fact
from app.schemas.llm import ChatIntent, ChatReply, Claim

CASES = [
    "22448 ka status kya hai?",
    "13427 Patna kab pahunchegi?",
    "Which stations cause the most delay in January?",
    "Monsoon mein Konkan route pe sabse zyada delay kahan hota hai?",
]


def _resolved_station(catalog: Catalog, intent: ChatIntent) -> str | None:
    codes = catalog.network.find_stations(intent.station)
    train = catalog.network.train(intent.train_number)
    if train and len(codes) > 1:
        codes = [c for c in codes if c in train.codes]
    return codes[0] if len(codes) == 1 else None


def test_demo_parser_reads_every_labelled_message(catalog: Catalog, chat_cases: list[dict]) -> None:
    for case in chat_cases:
        intent = parse_message(case["message"], catalog.network)
        got = (intent.kind, intent.train_number, sorted(intent.months), intent.language)
        want = (case["kind"], case["train"], sorted(case["months"]), case["language"])
        assert got == want, case["message"]
        assert _resolved_station(catalog, intent) == case["station"], case["message"]


def test_every_example_in_chat_json_parses(catalog: Catalog) -> None:
    for example in catalog.chat.examples:
        assert parse_message(example, catalog.network).kind != "help", example


def test_station_names_codes_and_old_names(catalog: Catalog) -> None:
    network = catalog.network
    assert network.find_stations("Allahabad") == ["PRYJ"]
    assert network.find_stations("mughalsarai") == ["DDU"]
    assert network.find_stations("cnb") == ["CNB"]  # a bare code, any case
    assert network.find_stations("Mumbai") == ["CSMT", "BCT"]
    assert network.find_stations("Mumbai Central") == ["BCT"]
    assert network.find_stations("ara mein") == []  # lower-case codes are words, not stations


async def test_status_answer_has_card_badge_and_cites_facts(seeded: Container) -> None:
    result = await seeded.chat.ask("13427 Patna kab pahunchegi?")
    assert result.kind == "train_status" and result.station == "PNBE"
    assert result.status is not None and result.status.state == "running"
    assert result.badge is not None and result.badge.station == "PNBE"
    assert result.dropped_claims == [] and result.claims
    assert all(i in result.facts for c in result.claims for i in c.fact_ids)
    assert "13427" in result.answer and "Patna Jn" in result.answer
    assert result.context.train_number == "13427"


async def test_no_train_means_a_question_then_the_context_carries_the_station(
    seeded: Container,
) -> None:
    first = await seeded.chat.ask("Is my train to Kanpur late?")
    assert first.clarify is not None and first.status is None
    assert first.context.pending == "train_status" and first.context.station == "CNB"
    second = await seeded.chat.ask("22448", first.context)
    assert second.clarify is None and second.train_number == "22448" and second.station == "CNB"
    assert second.badge is not None and second.badge.station == "CNB"


async def test_unknown_train_is_never_guessed(seeded: Container) -> None:
    result = await seeded.chat.ask("12999 ka status batao")
    assert result.clarify is not None and result.status is None
    assert "12999" in result.clarify.question
    assert all(o.value.isdigit() for o in result.clarify.options)


async def test_a_name_shared_by_two_directions_asks_which(seeded: Container) -> None:
    result = await seeded.chat.ask("Purvai Superfast kahan hai?")
    assert result.clarify is not None
    assert {o.value for o in result.clarify.options} == {"22447", "22448"}


async def test_a_station_off_the_route_asks_again(seeded: Container) -> None:
    result = await seeded.chat.ask("status of 22957 at CNB")
    assert result.clarify is not None and "does not stop" in result.clarify.question
    assert result.context.train_number == "22957"
    follow = await seeded.chat.ask("KOTA", result.context)
    assert follow.clarify is None and follow.station == "KOTA"


async def test_a_shared_city_name_resolves_by_route(seeded: Container) -> None:
    konkan = await seeded.chat.ask("Is 10147 late at Mumbai?")
    western = await seeded.chat.ask("Will 22958 be late at Mumbai?")
    assert (konkan.station, western.station) == ("CSMT", "BCT")


async def test_hotspots_answer(seeded: Container) -> None:
    result = await seeded.chat.ask("Which stations cause the most delay in January?")
    assert result.kind == "hotspots" and result.hotspot_months == [1]
    assert result.hotspots[0].code in {"CNB", "TDL", "ETW"}
    assert result.dropped_claims == []
    assert "inherited" in result.answer


async def test_every_example_question_answers_without_dropped_claims(seeded: Container) -> None:
    for example in seeded.catalog.chat.examples:
        result = await seeded.chat.ask(example)
        assert result.dropped_claims == [], example
        assert result.answer, example


def test_citation_check() -> None:
    facts = {
        f.id: f
        for f in [
            fact("live.delay_min", "Delay now", 34.6, "min"),
            fact("live.next.eta_p50", "Likely arrival", "14:55"),
            fact("train.number", "Train number", "22448"),
        ]
    }
    kept, dropped = check_claims(
        [
            Claim(text="22448 is 35 min late.", fact_ids=["train.number", "live.delay_min"]),
            Claim(text="It reaches at 14:55.", fact_ids=["live.next.eta_p50"]),
            Claim(text="It reaches at 15:10.", fact_ids=["live.next.eta_p50"]),
            Claim(text="It is 35 min late.", fact_ids=["live.delay_min", "made.up"]),
            Claim(text="It is very late.", fact_ids=[]),
        ],
        facts,
    )
    assert [c.text for c in kept] == ["22448 is 35 min late.", "It reaches at 14:55."]
    assert len(dropped) == 3
    assert numbers_in("at 14:55, 1,200 km") == ["14", "55", "1200"]


@pytest.mark.parametrize("message", CASES)
async def test_an_invented_number_is_dropped_and_the_template_answers(
    seeded: Container, message: str
) -> None:
    demo = build_demo_llm(seeded.catalog)
    llm = FakeLLM(
        responders={
            ChatIntent: demo.responders[ChatIntent],
            ChatReply: lambda _s, _c: ChatReply(
                claims=[Claim(text="It will be 999 min late.", fact_ids=["train.number"])]
            ),
        }
    )
    agent = ChatAgent(
        llm=llm,
        catalog=seeded.catalog,
        live=seeded.live,
        analytics=seeded.analytics,
        intent_effort="low",
        model_label="test",
    )
    result = await agent.ask(message, ChatContext())
    assert result.dropped_claims == ["It will be 999 min late."]
    assert result.claims and "999" not in result.answer
