"""How late each train usually is: the numbers behind the history badge.

For every train and stop, over the last ``badge_window_days`` of history: how many runs,
mean, median and 90th-percentile arrival delay, and the share of runs on time (within
``on_time_minutes``, 15 by default, the threshold Indian Railways punctuality is usually
reported against). Plus the same per calendar month over the whole history, so the badge
can say "last December it averaged 74 min" when the recent window misses the season.

The median and p90 matter as much as the mean: delays are skewed (most runs a few minutes
late, a few runs hours late), so a mean alone overstates the typical day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from app.core.catalog import AnalysisConfig, Network
from app.schemas.analysis import (
    Badge,
    DelayStats,
    Fact,
    ReliabilityReport,
    TrainReliability,
    fact,
)


def delay_stats(values: pd.Series | np.ndarray, on_time_minutes: int) -> DelayStats:
    array = np.asarray(values, dtype=float)
    array = array[~np.isnan(array)]
    if not len(array):
        return DelayStats(n=0, mean=0.0, median=0.0, p90=0.0, on_time_pct=0.0)
    return DelayStats(
        n=len(array),
        mean=float(array.mean()),
        median=float(np.median(array)),
        p90=float(np.quantile(array, 0.9)),
        on_time_pct=float((array <= on_time_minutes).mean() * 100),
    )


@dataclass
class ReliabilityIndex:
    report: ReliabilityReport
    by_stop: dict[tuple[str, str], DelayStats] = field(default_factory=dict)
    by_stop_month: dict[tuple[str, str, int], DelayStats] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)

    def badge(self, train_no: str, station: str, month: int | None = None) -> Badge | None:
        stats = self.by_stop.get((train_no, station))
        if stats is None or stats.n == 0:
            return None
        seasonal = self.by_stop_month.get((train_no, station, month)) if month else None
        return Badge(
            train_no=train_no,
            station=station,
            station_name=self.names.get(station, station),
            window_days=self.report.window_days,
            n=stats.n,
            mean=stats.mean,
            median=stats.median,
            p90=stats.p90,
            on_time_pct=stats.on_time_pct,
            month=month if seasonal else None,
            month_mean=seasonal.mean if seasonal else None,
            month_n=seasonal.n if seasonal else None,
        )


def reliability(stops: pd.DataFrame, network: Network, config: AnalysisConfig) -> ReliabilityIndex:
    on_time = config.on_time_minutes
    as_of = stops["run_date"].max()
    start = as_of - timedelta(days=config.badge_window_days - 1)
    observed = stops[(stops["seq"] > 0) & stops["arr_delay"].notna()]
    window = observed[observed["run_date"] >= start]

    by_stop = {
        (str(train), str(station)): delay_stats(group["arr_delay"], on_time)
        for (train, station), group in window.groupby(["train_no", "station"])
    }
    by_stop_month = {
        (str(train), str(station), int(month)): delay_stats(group["arr_delay"], on_time)
        for (train, station, month), group in observed.groupby(["train_no", "station", "month"])
    }

    trains: list[TrainReliability] = []
    for train in network.trains:
        stats = by_stop.get((train.number, train.to))
        trains.append(
            TrainReliability(
                number=train.number,
                name=train.name,
                from_station=train.from_,
                to_station=train.to,
                destination=stats,
            )
        )
    scored = [t for t in trains if t.destination and t.destination.n]
    most_late = min(scored, key=lambda t: (t.destination.on_time_pct, -t.destination.mean))  # type: ignore[union-attr]
    most_on_time = max(scored, key=lambda t: (t.destination.on_time_pct, -t.destination.mean))  # type: ignore[union-attr]
    most_late.label = "chronically_late"
    most_on_time.label = "reliable"

    report = ReliabilityReport(
        as_of=as_of.date(),
        window_start=start.date(),
        window_days=config.badge_window_days,
        on_time_minutes=on_time,
        trains=trains,
        most_late=most_late.number,
        most_on_time=most_on_time.number,
        facts=_facts(trains, most_late, most_on_time, config),
    )
    names = {s.code: s.name for s in network.stations}
    return ReliabilityIndex(
        report=report, by_stop=by_stop, by_stop_month=by_stop_month, names=names
    )


def _facts(
    trains: list[TrainReliability],
    most_late: TrainReliability,
    most_on_time: TrainReliability,
    config: AnalysisConfig,
) -> list[Fact]:
    days = config.badge_window_days
    facts = [
        fact(
            "reliability.window_days", "Days of history the reliability numbers cover", days, "days"
        ),
        fact(
            "reliability.on_time_minutes",
            "Arrival counts as on time within",
            config.on_time_minutes,
            "min",
        ),
        fact("reliability.most_late", "Least punctual train", most_late.number),
        fact("reliability.most_on_time", "Most punctual train", most_on_time.number),
    ]
    for train in trains:
        if not train.destination:
            continue
        prefix = f"train.{train.number}"
        stats = train.destination
        facts += [
            fact(f"{prefix}.name", f"Name of {train.number}", train.name),
            fact(
                f"{prefix}.on_time_pct",
                f"{train.number} on time at {train.to_station}",
                stats.on_time_pct,
                "%",
            ),
            fact(
                f"{prefix}.mean_delay",
                f"{train.number} mean arrival delay at {train.to_station}",
                stats.mean,
                "min",
            ),
            fact(
                f"{prefix}.median_delay",
                f"{train.number} median arrival delay at {train.to_station}",
                stats.median,
                "min",
            ),
        ]
    return facts
