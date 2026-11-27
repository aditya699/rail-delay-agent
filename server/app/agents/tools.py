"""Turn tool results into named facts: the only things the reply writer may say.

Times are facts too ("14:55"), so a reply cannot invent a clock time any more than a delay.
"""

from __future__ import annotations

from datetime import datetime

from app.analysis.stations import MONTHS
from app.core.catalog import Network, Train
from app.schemas.analysis import Badge, Fact, LiveStatus, StationReport, StopForecast, fact


def hhmm(value: datetime | None, today: datetime | None = None) -> str:
    """ "14:05", or "09:40, 28 Nov" when it falls on another day than ``today``."""
    if value is None:
        return ""
    text = value.strftime("%H:%M")
    if today is not None and value.date() != today.date():
        text += f", {value.day} {MONTHS[value.month - 1]}"
    return text


def train_facts(train: Train, network: Network) -> list[Fact]:
    return [
        fact("train.number", "Train number", train.number),
        fact("train.name", "Train name", train.name),
        fact("train.from", "Starts at", network.by_code[train.from_].name),
        fact("train.to", "Ends at", network.by_code[train.to].name),
    ]


def _forecast_facts(prefix: str, label: str, item: StopForecast, today: datetime) -> list[Fact]:
    return [
        fact(f"{prefix}.station", f"{label}: station code", item.station),
        fact(f"{prefix}.station_name", f"{label}: station", item.station_name),
        fact(f"{prefix}.sched", f"{label}: scheduled arrival", hhmm(item.sched_arr, today)),
        fact(f"{prefix}.eta_p50", f"{label}: likely arrival (p50)", hhmm(item.eta_p50, today)),
        fact(f"{prefix}.eta_p90", f"{label}: late case arrival (p90)", hhmm(item.eta_p90, today)),
        fact(f"{prefix}.p50_delay", f"{label}: likely delay", item.p50_delay, "min"),
        fact(f"{prefix}.p90_delay", f"{label}: late case delay", item.p90_delay, "min"),
    ]


def status_facts(
    status: LiveStatus, train: Train, target: str | None, network: Network
) -> list[Fact]:
    facts = [
        fact("live.state", "Run state", status.state),
        fact("live.clock", "Feed clock now", hhmm(status.clock)),
        fact("live.source", "Live source", status.source),
    ]
    if status.state == "not_started":
        facts += [
            fact(
                "live.scheduled_departure",
                "Scheduled departure",
                hhmm(status.scheduled_departure, status.clock),
            ),
            fact("live.origin", "Departs from", status.from_station),
        ]
        return facts
    facts += [
        fact("live.last_station", "Last reported station code", status.last_station or ""),
        fact("live.last_station_name", "Last reported station", status.last_station_name or ""),
        fact(
            "live.last_event",
            "Last event",
            "arrived at" if status.last_event == "arr" else "departed from",
        ),
        fact("live.last_event_at", "Time of last event", hhmm(status.last_event_at, status.clock)),
        fact("live.delay_min", "Delay now", status.delay_min or 0, "min"),
    ]
    if status.usual_median is not None:
        facts += [
            fact("live.unusual", "Today's delay is unusual for this train here", status.unusual),
            fact("live.usual_median", "Usual (median) delay here", status.usual_median, "min"),
            fact("live.usual_p90", "Bad-day (p90) delay here", status.usual_p90 or 0.0, "min"),
        ]
    if not status.forecasts:
        return facts
    first = status.forecasts[0]
    facts += _forecast_facts("live.next", "Next stop", first, status.clock)
    by_station = {f.station: f for f in status.forecasts}
    if target and target != first.station:
        if target in by_station:
            facts += _forecast_facts(
                "live.target", "Your station", by_station[target], status.clock
            )
        else:
            seq = train.seq(target)
            if (
                seq is not None
                and status.last_station
                and seq <= (train.seq(status.last_station) or 0)
            ):
                facts += [
                    fact("live.target.passed", "Your station is already behind it", True),
                    fact("live.target.station_name", "Your station", network.by_code[target].name),
                ]
    last = status.forecasts[-1]
    if last.station not in {first.station, target}:
        facts += _forecast_facts("live.destination", "Destination", last, status.clock)
    return facts


def badge_facts(badge: Badge, on_time_minutes: int) -> list[Fact]:
    facts = [
        fact("badge.station", "Badge station code", badge.station),
        fact("badge.station_name", "Badge station", badge.station_name),
        fact("badge.window_days", "History window", badge.window_days, "days"),
        fact("badge.n", "Runs in the window", badge.n),
        fact("badge.mean", "Mean arrival delay", badge.mean, "min"),
        fact("badge.median", "Median arrival delay", badge.median, "min"),
        fact("badge.p90", "90th percentile arrival delay", badge.p90, "min"),
        fact("badge.on_time_pct", "Runs on time", badge.on_time_pct, "%"),
        fact("badge.on_time_minutes", "On time means within", on_time_minutes, "min"),
    ]
    if badge.month and badge.month_mean is not None:
        facts += [
            fact("badge.month", "Month compared", MONTHS[badge.month - 1]),
            fact("badge.month_mean", "Mean arrival delay in that month", badge.month_mean, "min"),
            fact("badge.month_n", "Runs in that month", badge.month_n or 0),
        ]
    return facts


def hotspot_facts(report: StationReport) -> list[Fact]:
    return list(report.facts)
