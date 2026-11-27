"""The statistics, on hand-made rows and on the planted sample history."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analysis.dataset import arrivals, parse_raw, prepare
from app.analysis.reliability import delay_stats
from app.analysis.stations import cluster_bootstrap_ci, month_label
from app.container import Container
from app.core.catalog import Catalog


def _raw(rows: list[tuple[str, int, str, str, str, str, str]]) -> pd.DataFrame:
    columns = ["train_no", "seq", "station", "sched_arr", "act_arr", "sched_dep", "act_dep"]
    frame = pd.DataFrame(rows, columns=columns)
    frame.insert(0, "run_date", "2026-01-10")
    return parse_raw(frame.replace({"": None}))


def test_added_and_inherited_on_a_hand_made_run(catalog: Catalog) -> None:
    # Leaves New Delhi 10 late, gains 25 more before Kanpur, loses nothing to Prayagraj.
    raw = _raw(
        [
            ("14263", 0, "NDLS", "", "", "2026-01-10 06:00", "2026-01-10 06:10"),
            (
                "14263",
                1,
                "CNB",
                "2026-01-10 14:20",
                "2026-01-10 14:55",
                "2026-01-10 14:25",
                "2026-01-10 15:00",
            ),
            ("14263", 2, "PRYJ", "2026-01-10 17:55", "2026-01-10 18:30", "", ""),
        ]
    )
    stops = prepare(raw, catalog.network)
    cnb = stops[stops["station"] == "CNB"].iloc[0]
    assert cnb["arr_delay"] == 35 and cnb["inherited"] == 10 and cnb["added"] == 25
    pryj = stops[stops["station"] == "PRYJ"].iloc[0]
    assert pryj["arr_delay"] == 35 and pryj["inherited"] == 35 and pryj["added"] == 0
    assert bool(pryj["is_last"]) and pryj["month"] == 1 and pryj["hour"] == 17
    assert cnb["km"] > 300  # New Delhi to Kanpur, roughly, along the track


def test_added_plus_inherited_is_the_arrival_delay(seeded: Container) -> None:
    rows = arrivals(seeded.analytics.current.stops)
    assert np.allclose(rows["added"] + rows["inherited"], rows["arr_delay"])


def test_month_label() -> None:
    assert month_label([12, 1]) == "Dec, Jan"
    assert month_label([1, 2, 3]) == "Jan, Feb, Mar"
    assert month_label([7, 8]) == "Jul, Aug"
    assert month_label([]) == "all year"


def test_cluster_bootstrap_interval_brackets_the_mean() -> None:
    rng = np.random.default_rng(0)
    days = np.repeat(np.arange(60), 5)
    values = pd.Series(rng.normal(10, 3, 300) + np.repeat(rng.normal(0, 4, 60), 5))
    low, high = cluster_bootstrap_ci(values, pd.Series(days), 400, rng)
    assert low < values.mean() < high
    # Days share a shock, so resampling days gives a wider interval than resampling rows.
    rows_low, rows_high = cluster_bootstrap_ci(values, pd.Series(np.arange(300)), 400, rng)
    assert high - low > rows_high - rows_low


def test_delay_stats() -> None:
    stats = delay_stats(np.array([0, 5, 10, 20, 60, np.nan]), on_time_minutes=15)
    assert stats.n == 5 and stats.median == 10 and stats.on_time_pct == pytest.approx(60)


def test_hotspots_separate_added_from_inherited(seeded: Container, truth: dict) -> None:
    report = seeded.analytics.current.stations
    assert report.stations[0].code == truth["top_added_station"]
    top = report.stations[0]
    assert top.added_ci_low < top.added_mean < top.added_ci_high
    naive = next(s for s in report.stations if s.code == report.naive_top)
    assert naive.code in truth["inherits_most"]
    assert naive.added_share is not None and naive.added_share < 0.3
    assert naive.arrival_mean > top.arrival_mean  # a dashboard would blame the wrong station


def test_hotspots_by_month_find_fog_and_monsoon(seeded: Container, truth: dict) -> None:
    january = seeded.analytics.hotspots([1]).stations[:3]
    assert sum(s.code in truth["fog"]["stations"] for s in january) >= 2
    monsoon = seeded.analytics.hotspots([7, 8]).stations[0]
    assert monsoon.code in truth["monsoon"]["stations"]


def test_seasonal_months_and_the_junction_window(seeded: Container, truth: dict) -> None:
    season = seeded.analytics.current.seasonality
    months = {s.station: s.months for s in season.seasonal}
    for code in truth["fog"]["stations"]:
        assert months[code] == [1, 12], code
    for code in truth["monsoon"]["stations"]:
        assert months[code] == [7, 8], code
    assert months["DDU"] == []  # its problem is the hour, not the season
    window = next(w for w in season.windows if w.station == "DDU")
    start, end = truth["junction_window"]["hours"]
    assert set(window.hours) <= set(range(start, end))
    assert {w.station for w in season.windows} == {"DDU"}


def test_reliability_and_the_badge(seeded: Container, truth: dict) -> None:
    analytics = seeded.analytics.current
    report = analytics.reliability.report
    assert report.most_late == truth["chronically_late_train"]
    assert report.most_on_time == truth["reliable_train"]
    badge = analytics.reliability.badge("13427", "PNBE", month=1)
    assert badge is not None and badge.window_days == 90
    stops = analytics.stops
    window = stops[
        (stops["train_no"] == "13427")
        & (stops["station"] == "PNBE")
        & (stops["run_date"] >= pd.Timestamp(report.window_start))
    ]["arr_delay"].dropna()
    assert badge.n == len(window)
    assert badge.mean == pytest.approx(window.mean())
    assert badge.month == 1 and badge.month_mean is not None and badge.month_mean > badge.mean
    assert analytics.reliability.badge("13427", "BCT") is None
