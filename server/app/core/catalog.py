"""Editorial configuration, loaded from the data files in ``app/config/``.

* ``network.json``: stations (code, name, coordinates, aliases), names that mean more
  than one station, corridors for the map, and every train with its timetable.
  Resolving "Kanpur" or "Allahabad" to ``CNB``/``PRYJ`` is a lookup here; no model ever
  invents a station or a train.
* ``analysis.json``: the on-time threshold, the badge window, how big a seasonal or
  hour-of-day effect must be before it is reported, the "unusual today" rule and the
  forecast model's settings.
* ``chat.json``: example questions for the chat panel.

Adding a station or a train is an edit to ``network.json``, not to code.
"""

from __future__ import annotations

import json
import math
import re
from functools import cached_property
from pathlib import Path

from pydantic import BaseModel, Field

TRACK_FACTOR = 1.22
"""Track is longer than the straight line between two stations; a rough constant."""


class Station(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    aliases: list[str] = Field(default_factory=list)


class Stop(BaseModel):
    station: str
    arr: str | None = None
    dep: str | None = None


class Train(BaseModel):
    number: str
    name: str
    kind: str
    from_: str = Field(alias="from")
    to: str
    aliases: list[str] = Field(default_factory=list)
    stops: list[Stop]

    model_config = {"populate_by_name": True}

    @property
    def codes(self) -> list[str]:
        return [stop.station for stop in self.stops]

    def seq(self, code: str) -> int | None:
        return next((i for i, s in enumerate(self.stops) if s.station == code), None)

    @property
    def label(self) -> str:
        return f"{self.number} {self.name}"


class Corridor(BaseModel):
    id: str
    name: str
    stations: list[str]


def normalise(text: str) -> str:
    return re.sub(r"[\s\-_.]+", " ", text.lower()).strip()


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in normalise(phrase).split()]
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-_.]+".join(words) + r"(?![a-z0-9])")


def haversine_km(a: Station, b: Station) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) * TRACK_FACTOR


class Network(BaseModel):
    stations: list[Station]
    ambiguous_names: dict[str, list[str]] = Field(default_factory=dict)
    corridors: list[Corridor] = Field(default_factory=list)
    trains: list[Train]

    @cached_property
    def by_code(self) -> dict[str, Station]:
        return {s.code: s for s in self.stations}

    @cached_property
    def by_number(self) -> dict[str, Train]:
        return {t.number: t for t in self.trains}

    def station(self, code: str) -> Station | None:
        return self.by_code.get(code.upper()) if code else None

    def train(self, number: str | None) -> Train | None:
        return self.by_number.get(number.strip()) if number else None

    def segment_km(self, a: str, b: str) -> float:
        return haversine_km(self.by_code[a], self.by_code[b])

    @cached_property
    def _station_patterns(self) -> list[tuple[re.Pattern[str], list[str], str]]:
        entries: list[tuple[re.Pattern[str], list[str], str]] = []
        for station in self.stations:
            for name in sorted({station.name, *station.aliases}):
                entries.append((phrase_pattern(name), [station.code], name))
        for name, codes in self.ambiguous_names.items():
            entries.append((phrase_pattern(name), list(codes), name))
        # Longest name first, so "Mumbai Central" beats "Mumbai".
        entries.sort(key=lambda entry: -len(normalise(entry[2])))
        return entries

    def station_mention(self, text: str | None) -> str | None:
        """The station name, alias or capitalised code written in ``text``, as written."""
        if not text:
            return None
        for code in re.findall(r"\b[A-Z]{2,5}\b", text):
            if code in self.by_code:
                return code
        haystack = normalise(text)
        for pattern, _, name in self._station_patterns:
            if pattern.search(haystack):
                return name
        return None

    def find_stations(self, text: str | None) -> list[str]:
        """Candidate station codes named in ``text``: one code, several (ambiguous), or none.

        Codes match only when written in capitals ("CNB"), because several are ordinary
        words in lower case ("ara", "st"), unless the whole text is just the code ("cnb").
        Names and aliases match in any case.
        """
        if not text:
            return []
        if text.strip().upper() in self.by_code:
            return [text.strip().upper()]
        for code in re.findall(r"\b[A-Z]{2,5}\b", text):
            if code in self.by_code:
                return [code]
        haystack = normalise(text)
        for pattern, codes, _ in self._station_patterns:
            if pattern.search(haystack):
                return codes
        return []

    def find_train_by_name(self, text: str | None) -> list[Train]:
        """Trains whose name or alias appears in ``text`` (both directions share a name)."""
        if not text:
            return []
        haystack = normalise(text)
        found = []
        for train in self.trains:
            names = {train.name, *train.aliases}
            if any(phrase_pattern(name).search(haystack) for name in names):
                found.append(train)
        return found


class SeasonRule(BaseModel):
    min_excess_min: float = 8.0
    min_rows: int = 30


class HourRule(BaseModel):
    min_excess_min: float = 10.0
    min_rows: int = 30


class UnusualRule(BaseModel):
    over_p90_min: float = 15.0
    over_median_min: float = 30.0
    min_runs: int = 10


class ModelConfig(BaseModel):
    test_days: int = 90
    max_train_rows: int = 40000
    max_iter: int = 150
    learning_rate: float = 0.08
    max_leaf_nodes: int = 31
    seed: int = 7


class AnalysisConfig(BaseModel):
    on_time_minutes: int = 15
    badge_window_days: int = 90
    bootstrap_reps: int = 400
    hotspot_top_n: int = 5
    min_rows_per_station: int = 30
    season: SeasonRule = Field(default_factory=SeasonRule)
    hour: HourRule = Field(default_factory=HourRule)
    unusual: UnusualRule = Field(default_factory=UnusualRule)
    model: ModelConfig = Field(default_factory=ModelConfig)


class ChatConfig(BaseModel):
    examples: list[str] = Field(default_factory=list)


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text("utf-8"))
    data.pop("_note", None)
    return data


class Catalog:
    """Everything editorial, read from ``config_dir``. Cheap to rebuild; files are small."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.network = Network.model_validate(_read_json(config_dir / "network.json"))
        self.analysis = AnalysisConfig.model_validate(_read_json(config_dir / "analysis.json"))
        self.chat = ChatConfig.model_validate(_read_json(config_dir / "chat.json"))

    def reload_analysis(self) -> AnalysisConfig:
        """Re-read ``analysis.json`` (each rebuild picks up threshold edits)."""
        self.analysis = AnalysisConfig.model_validate(_read_json(self.config_dir / "analysis.json"))
        return self.analysis
