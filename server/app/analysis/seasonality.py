"""When stations add delay: by month of the year and by hour of the day.

* **Month x station heatmap** of mean added delay. A month is *seasonal* for a station
  when its mean is well above the station's median month (``season.min_excess_min``).
  Medians, not means, so one bad month does not raise the bar for itself.
* **Hour of day** per station, with each station's seasonal months **left out**. Fog is
  worst at night, so without that step every night-time arrival on the fog stretch would
  look like an hour-of-day problem when it is really a winter problem.

Hours are scheduled arrival hours. A station only has the hours its trains are timetabled
at, so read a window as "trains due here 18:00-21:00 lose time", not as a full 24h curve.
"""

from __future__ import annotations

import pandas as pd

from app.analysis.dataset import arrivals
from app.analysis.stations import MONTHS, month_label
from app.core.catalog import AnalysisConfig
from app.schemas.analysis import (
    Fact,
    HeatCell,
    HourCell,
    HourWindow,
    SeasonalityReport,
    SeasonalStation,
    fact,
)


def seasonality(stops: pd.DataFrame, config: AnalysisConfig) -> SeasonalityReport:
    rows = arrivals(stops)
    by_month = rows.groupby(["station", "month"])["added"].agg(["mean", "count"]).reset_index()
    cells = [
        HeatCell(
            station=r.station, month=int(r.month), n=int(r["count"]), added_mean=float(r["mean"])
        )
        for _, r in by_month.iterrows()
    ]

    seasonal: list[SeasonalStation] = []
    seasonal_months: dict[str, list[int]] = {}
    for code, group in by_month.groupby("station"):
        usable = group[group["count"] >= config.season.min_rows]
        if usable.empty:
            continue
        baseline = float(usable["mean"].median())
        flagged = usable[usable["mean"] - baseline >= config.season.min_excess_min]
        peak = usable.loc[usable["mean"].idxmax()]
        months = sorted(int(m) for m in flagged["month"])
        seasonal_months[str(code)] = months
        seasonal.append(
            SeasonalStation(
                station=str(code),
                baseline=baseline,
                months=months,
                peak_month=int(peak["month"]),
                peak_added=float(peak["mean"]),
            )
        )

    # Hour of day, each station's seasonal months excluded.
    keep = [
        month not in seasonal_months.get(station, [])
        for station, month in zip(rows["station"], rows["month"], strict=True)
    ]
    off_season = rows[keep]
    by_hour = off_season.groupby(["station", "hour"])["added"].agg(["mean", "count"]).reset_index()
    hours = [
        HourCell(
            station=r.station, hour=int(r.hour), n=int(r["count"]), added_mean=float(r["mean"])
        )
        for _, r in by_hour.iterrows()
    ]
    windows: list[HourWindow] = []
    for code, group in by_hour.groupby("station"):
        usable = group[group["count"] >= config.hour.min_rows]
        if len(usable) < 2:
            continue
        median = float(usable["mean"].median())
        flagged = usable[usable["mean"] - median >= config.hour.min_excess_min]
        for run in _consecutive(sorted(int(h) for h in flagged["hour"])):
            inside = usable[usable["hour"].isin(run)]
            mean = float((inside["mean"] * inside["count"]).sum() / inside["count"].sum())
            windows.append(
                HourWindow(
                    station=str(code),
                    hours=run,
                    label=f"{run[0]:02d}:00-{(run[-1] + 1) % 24:02d}:00",
                    excess=mean - median,
                )
            )
    windows.sort(key=lambda w: -w.excess)

    return SeasonalityReport(
        cells=cells,
        seasonal=seasonal,
        hours=hours,
        windows=windows,
        facts=_facts(seasonal, windows),
    )


def _consecutive(hours: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for hour in hours:
        if runs and hour == runs[-1][-1] + 1:
            runs[-1].append(hour)
        else:
            runs.append([hour])
    return runs


def _facts(seasonal: list[SeasonalStation], windows: list[HourWindow]) -> list[Fact]:
    facts: list[Fact] = []
    for item in seasonal:
        prefix = f"season.{item.station}"
        facts += [
            fact(
                f"{prefix}.months",
                f"Months {item.station} adds unusual delay",
                month_label(item.months) if item.months else "none",
            ),
            fact(
                f"{prefix}.peak_month",
                f"Worst month at {item.station}",
                MONTHS[item.peak_month - 1],
            ),
            fact(
                f"{prefix}.peak_added",
                f"Mean added delay at {item.station} in its worst month",
                item.peak_added,
                "min",
            ),
            fact(
                f"{prefix}.baseline",
                f"Mean added delay at {item.station} in a typical month",
                item.baseline,
                "min",
            ),
        ]
    seen: set[str] = set()
    for window in windows:  # worst first; one window per station in the facts
        if window.station in seen:
            continue
        seen.add(window.station)
        prefix = f"hours.{window.station}"
        facts += [
            fact(
                f"{prefix}.window",
                f"Hours trains due at {window.station} lose most time",
                window.label,
            ),
            fact(
                f"{prefix}.excess",
                f"Extra delay added at {window.station} in that window",
                window.excess,
                "min",
            ),
        ]
    return facts
