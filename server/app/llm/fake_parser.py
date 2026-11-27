"""Keyword rules that turn a passenger's message into a :class:`ChatIntent`, offline.

Demo mode's stand-in for Claude's intent step. It understands the patterns in
``chat.json`` and ``samples/chat_eval.json`` (English and Hinglish) and is crude on
purpose: anything it misreads still goes through the same validation as Claude's answer,
so a wrong guess ends in a clarifying question, never in a made-up train.
"""

from __future__ import annotations

import re

from app.core.catalog import Network, normalise
from app.schemas.llm import ChatIntent, IntentKind

TRAIN_NUMBER = re.compile(r"(?<!\d)(\d{5})(?!\d)")

MONTH_WORDS = {
    1: ["january", "jan", "janvari"],
    2: ["february", "feb", "farvari"],
    3: ["march", "mar"],
    4: ["april", "apr"],
    5: ["may"],
    6: ["june", "jun"],
    7: ["july", "jul", "julai"],
    8: ["august", "aug", "agast"],
    9: ["september", "sep", "sept"],
    10: ["october", "oct"],
    11: ["november", "nov"],
    12: ["december", "dec", "disambar"],
}
SEASONS = {
    (12, 1): [
        "winter",
        "winters",
        "fog",
        "foggy",
        "sardi",
        "sardiyon",
        "sardiyo",
        "kohra",
        "thand",
    ],
    (7, 8): ["monsoon", "rain", "rains", "rainy", "baarish", "barish", "barsaat", "baarishon"],
}

HOTSPOT = [
    "which station",
    "which stations",
    "kaunsa station",
    "kaunse station",
    "kis station",
    "kin stations",
    "most delay",
    "sabse zyada delay",
    "sabse jyada delay",
    "zyada delay kahan",
    "delay kahan",
    "hotspot",
    "hotspots",
    "worst station",
    "worst stations",
    "where do trains lose",
    "cause the most",
    "causes the most",
]
HISTORY = [
    "usually",
    "usual",
    "generally",
    "on average",
    "average",
    "aam taur",
    "aamtaur",
    "hamesha",
    "kitni late hoti",
    "kitna late hoti",
    "late hoti hai",
    "late rehti",
    "reliable",
    "punctual",
    "on time percent",
    "track record",
    "history",
]
STATUS = [
    "status",
    "where is",
    "kahan hai",
    "kaha hai",
    "kidhar",
    "late",
    "running",
    "chal rahi",
    "pahunchegi",
    "pahunch",
    "reach",
    "arrive",
    "eta",
    "kab tak",
    "kab aayegi",
    "kab",
]
HINGLISH = {
    "ka",
    "ki",
    "ke",
    "hai",
    "kya",
    "kab",
    "kahan",
    "kaha",
    "kitni",
    "kitna",
    "mein",
    "sabse",
    "zyada",
    "jyada",
    "kaunsa",
    "kaunse",
    "kis",
    "meri",
    "mera",
    "chal",
    "rahi",
    "hogi",
    "pahunchegi",
    "hoti",
    "pe",
    "aur",
    "abhi",
    "batao",
    "bata",
    "yeh",
    "kyun",
    "hota",
}


def _has(text: str, phrases: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", text) for p in phrases)


def parse_message(message: str, network: Network, pending: IntentKind | None = None) -> ChatIntent:
    text = normalise(message)
    words = set(text.split())

    number_match = TRAIN_NUMBER.search(message)
    number = number_match.group(1) if number_match else None
    named = network.find_train_by_name(message)
    station = network.station_mention(message)
    # A station inside a train name ("Ganga Shuttle") is part of the name, not a station.
    if station and named and any(normalise(station) in normalise(t.name) for t in named):
        station = None

    months: list[int] = []
    for month, names in MONTH_WORDS.items():
        if _has(text, names):
            months.append(month)
    for season, names in SEASONS.items():
        if _has(text, names):
            months += [m for m in season if m not in months]

    kind: IntentKind
    if _has(text, HOTSPOT) and not number and not named:
        kind = "hotspots"
    elif _has(text, HISTORY) and (number or named or pending in ("train_status", "train_history")):
        kind = "train_history"
    elif _has(text, STATUS) or number or named:
        kind = "train_status"
    elif months and _has(text, ["delay", "late"]):
        kind = "hotspots"
    else:
        kind = "help"
    if kind == "help" and pending and (number or named or station):
        kind = pending  # the answer to a clarifying question
    if kind == "train_status" and _has(text, HISTORY) and not number and not named:
        kind = "train_history"

    return ChatIntent(
        kind=kind,
        train_number=number,
        train_name=named[0].name if named and not number else None,
        station=station,
        months=months,
        language="hinglish" if len(words & HINGLISH) >= 1 else "english",
    )
