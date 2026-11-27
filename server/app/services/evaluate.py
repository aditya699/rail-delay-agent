"""Score the whole pipeline against what ``make_samples.py`` planted.

``samples/ground_truth.json`` says where fog and monsoon were added and in which months,
which junction has an evening window, which train is always late and which is always on
time, and which live arrival is the unusual one. ``samples/chat_eval.json`` holds
labelled passenger messages. Every check here compares a computed result with that truth:

* **analysis**: hotspot ranking (added vs inherited), seasonal months per station, the
  hour-of-day window, the least and most punctual trains;
* **forecast**: beats persistence on held-out days, p90 coverage in a sane band, and the
  same on the live replay (forecasts made at each departure, scored at each arrival);
* **live**: the planted incident is flagged unusual, and almost nothing else is;
* **chat**: intent accuracy on the labelled messages, clarifying questions where they are
  due, and no reply sentence dropped for citing something that was not computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.agents.chat import ChatContext
from app.container import Container
from app.ingest.live import SimulatedLiveSource


@dataclass
class Section:
    name: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": label, "passed": bool(passed), "detail": detail})

    @property
    def passed(self) -> int:
        return sum(c["passed"] for c in self.checks)


def score_analysis(container: Container, truth: dict[str, Any]) -> Section:
    section = Section("analysis")
    analytics = container.analytics.current
    stations = analytics.stations
    top = stations.stations[0].code
    section.check(
        "top added-delay station",
        top == truth["top_added_station"],
        f"{top}, planted {truth['top_added_station']}",
    )
    naive = next(s for s in stations.stations if s.code == stations.naive_top)
    section.check(
        "worst arrival delay is inherited, not added",
        naive.code in truth["inherits_most"]
        and naive.code != top
        and (naive.added_share or 0) < 0.3,
        f"{naive.code}: {naive.arrival_mean:.0f} min arrival delay, "
        f"{naive.added_mean:.0f} min added",
    )
    seasonal = {s.station: set(s.months) for s in analytics.seasonality.seasonal}
    for key in ("fog", "monsoon"):
        want = set(truth[key]["months"])
        found = [code for code in truth[key]["stations"] if seasonal.get(code) == want]
        missed = [
            f"{c}: {sorted(seasonal.get(c, set()))}"
            for c in truth[key]["stations"]
            if c not in found
        ]
        section.check(
            f"{key} months found at every planted station",
            not missed,
            f"{len(found)}/{len(truth[key]['stations'])}"
            + (f"; {', '.join(missed)}" if missed else ""),
        )
    planted = set(truth["fog"]["stations"]) | set(truth["monsoon"]["stations"])
    planted |= set(truth["fog"].get("light_stations", []))
    others = [c for c, months in seasonal.items() if months and c not in planted]
    section.check(
        "no seasonal months where none were planted", not others, ", ".join(others) or "none"
    )
    window = truth["junction_window"]
    windows = analytics.seasonality.windows
    hours = set(range(window["hours"][0], window["hours"][1]))
    found = [w for w in windows if w.station == window["station"]]
    section.check(
        f"{window['station']} evening window found",
        bool(found) and set(found[0].hours) <= hours,
        found[0].label if found else "no window",
    )
    stray = [f"{w.station} {w.label}" for w in windows if w.station != window["station"]]
    section.check("no other hour-of-day window", not stray, ", ".join(stray) or "none")
    report = analytics.reliability.report
    section.check(
        "chronically late train",
        report.most_late == truth["chronically_late_train"],
        report.most_late,
    )
    section.check(
        "most punctual train", report.most_on_time == truth["reliable_train"], report.most_on_time
    )
    return section


def score_forecast(container: Container, truth: dict[str, Any]) -> Section:
    section = Section("forecast")
    card = container.analytics.current.card
    section.check(
        "beats persistence on held-out days",
        card.mae_model < card.mae_persistence,
        f"MAE {card.mae_model:.1f} vs {card.mae_persistence:.1f} min "
        f"({card.mae_improvement_pct:.0f}% better)",
    )
    low, high = truth["model"]["p90_coverage_band"]
    section.check(
        "p90 coverage in band",
        low <= card.p90_coverage <= high,
        f"{card.p90_coverage:.1%} (band {low:.0%}-{high:.0%})",
    )
    source = container.live.source
    if isinstance(source, SimulatedLiveSource):
        model_err, persist_err = _replay_errors(container, source)
        section.check(
            "beats persistence on the live replay",
            model_err < persist_err,
            f"MAE {model_err:.1f} vs {persist_err:.1f} min",
        )
    return section


def _replay_errors(container: Container, source: SimulatedLiveSource) -> tuple[float, float]:
    """Forecast from every departure in the replay; score against the actual arrivals."""
    forecaster = container.analytics.current.forecaster
    network = container.catalog.network
    arrivals = {
        (e.train_no, e.run_date, e.seq): e.delay_min for e in source.events if e.event == "arr"
    }
    model, persist = [], []
    for event in source.events:
        if event.event != "dep":
            continue
        train = network.by_number[event.train_no]
        current = max(event.delay_min, 0)
        for item in forecaster.forecast(train, event.run_date, event.seq, current):
            actual = arrivals.get((event.train_no, event.run_date, item.seq))
            if actual is not None:
                model.append(abs(actual - item.p50_delay))
                persist.append(abs(actual - current))
    return float(np.mean(model)), float(np.mean(persist))


async def score_live(container: Container, truth: dict[str, Any]) -> Section:
    section = Section("live")
    source = container.live.source
    if not isinstance(source, SimulatedLiveSource):
        section.check("simulated source", False, "live checks need LIVE_SOURCE=simulated")
        return section
    end = datetime.combine(source.run_dates[-1] + timedelta(days=2), datetime.min.time())
    await container.live.poll_once(until=end)
    flagged = container.live.unusual_today(clock=end - timedelta(days=1))
    found = {(u.train_no, u.station, u.run_date.isoformat()) for u in flagged}
    for incident in truth["unusual_today"]:
        key = (incident["train"], incident["station"], incident["run_date"])
        section.check(
            f"incident flagged: {key[0]} at {key[1]}", key in found, f"{len(flagged)} flagged"
        )
    extra = found - {(i["train"], i["station"], i["run_date"]) for i in truth["unusual_today"]}
    section.check(
        "at most 2 other arrivals flagged",
        len(extra) <= 2,
        ", ".join(f"{t} {s}" for t, s, _ in extra) or "none",
    )
    return section


async def score_chat(container: Container, cases: list[dict[str, Any]]) -> Section:
    section = Section("chat")
    network = container.catalog.network
    hits = 0
    misses = []
    for case in cases:
        intent = await container.chat.parse(case["message"], ChatContext())
        station = None
        if intent.station:
            codes = network.find_stations(intent.station)
            train = network.train(intent.train_number)
            if train and len(codes) > 1:
                codes = [c for c in codes if c in train.codes]
            station = codes[0] if len(codes) == 1 else None
        got = (intent.kind, intent.train_number, station, sorted(intent.months), intent.language)
        want = (
            case["kind"],
            case["train"],
            case["station"],
            sorted(case["months"]),
            case["language"],
        )
        if got == want:
            hits += 1
        else:
            misses.append(f"{case['message']!r}: got {got}")
    accuracy = hits / len(cases)
    section.check(
        "intent accuracy >= 90%",
        accuracy >= 0.9,
        f"{hits}/{len(cases)}" + ("; " + "; ".join(misses) if misses else ""),
    )

    wrong = []
    for case in cases:
        result = await container.chat.ask(case["message"])
        if bool(case.get("clarify")) != (result.clarify is not None):
            wrong.append(case["message"])
    section.check(
        "clarifies exactly when it should", not wrong, ", ".join(wrong) or f"{len(cases)} messages"
    )

    dropped = 0
    for example in container.catalog.chat.examples:
        result = await container.chat.ask(example)
        dropped += len(result.dropped_claims)
    section.check("replies cite only computed facts", dropped == 0, f"{dropped} claims dropped")
    return section


async def evaluate(
    container: Container, truth: dict[str, Any], cases: list[dict[str, Any]]
) -> list[Section]:
    """Every section. Needs the analytics built; replays the whole live feed."""
    sections = [score_analysis(container, truth), score_forecast(container, truth)]
    sections.append(await score_live(container, truth))
    sections.append(await score_chat(container, cases))
    return sections
