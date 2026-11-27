"""Simulate a year of train running on the demo network, with patterns planted to be found.

    cd server
    uv run python scripts/make_samples.py

Writes, into ``samples/``:

* ``history.csv.gz``: one row per train, run date and stop, 2025-11-01 to 2026-11-25:
  scheduled and actual arrival and departure. This is what the analysis learns from.
* ``live_replay.csv``: the same for 2026-11-26 and 2026-11-27, held out of the history.
  The simulated live source replays it on an accelerated clock, as if a running-status
  feed were reporting each arrival and departure as it happens.
* ``ground_truth.json``: what was planted, so ``python -m app.cli eval`` can score the
  analysis, the forecast and the chatbot against it.

The stations and their coordinates are real (approximately). Every train, number, name,
timetable and minute of delay is made up. Seeded, so every run gives the same files.

Planted, on top of everyday noise and rare random incidents:

1. **Winter fog** (December and January, a little in late November and early February)
   on the Delhi - Kanpur - Prayagraj stretch, worst at night and in the early morning,
   with a shared intensity per day (a foggy night is foggy for every train).
2. **Monsoon** (July and August, a little either side) on the Konkan stretch.
3. **An evening junction window**: arrivals at DDU scheduled 18:00-22:00 wait for a
   platform, all year round.
4. **One chronically late train** (13427, late from its origin and slow everywhere) and
   **one reliably on-time train** (22973).
5. **Propagation**: delay a train carries into a stop is carried out of it. A downstream
   station looks late because it inherits delay, not because it adds any.
6. **One unusual event in the live replay**: 10147 is held 80 minutes before Ratnagiri on
   2026-11-27, a day it is normally close to on time there.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SERVER_DIR.parent
NETWORK = SERVER_DIR / "app" / "config" / "network.json"
SAMPLES = REPO_DIR / "samples"

SEED = 20261127
HISTORY_START = date(2025, 11, 1)
HISTORY_END = date(2026, 11, 25)
LIVE_DATES = [date(2026, 11, 26), date(2026, 11, 27)]

FOG_WEIGHTS = {
    "NDLS": 0.3,
    "GZB": 0.5,
    "ALJN": 0.8,
    "TDL": 0.9,
    "ETW": 1.0,
    "CNB": 1.0,
    "PRYJ": 0.8,
}
FOG_RATE = 25.0  # minutes per 100 km of fog stretch, at full intensity
MONSOON_WEIGHTS = {"PNVL": 0.3, "RN": 1.0, "KUDL": 1.0, "MAO": 1.0, "KAWR": 0.7, "UD": 0.5}
MONSOON_RATE = 25.0
JUNCTION = "DDU"
JUNCTION_HOURS = (18, 22)
CHRONIC = "13427"
RELIABLE = "22973"
INCIDENT = {"train": "10147", "station": "RN", "run_date": "2026-11-27", "added_min": 80}

COLUMNS = ["run_date", "train_no", "seq", "station", "sched_arr", "act_arr", "sched_dep", "act_dep"]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) * 1.22


def fog_scale(day: date) -> float:
    if day.month in (12, 1):
        return 1.0
    if day.month == 2 and day.day <= 15:
        return 0.3
    if day.month == 11 and day.day >= 20:
        return 0.2
    return 0.0


def monsoon_scale(day: date) -> float:
    if day.month in (7, 8):
        return 1.0
    if (day.month == 6 and day.day >= 15) or (day.month == 9 and day.day <= 15):
        return 0.35
    return 0.0


def fog_hour_factor(hour: int) -> float:
    """Fog is densest from late evening to mid-morning."""
    return 1.0 if hour >= 21 or hour < 10 else 0.45


def timetable(train: dict, run_date: date) -> list[tuple[datetime | None, datetime | None]]:
    """Scheduled (arrival, departure) per stop; clock times roll over midnight."""
    out = []
    base = datetime(run_date.year, run_date.month, run_date.day)
    day = 0
    last = -1
    for stop in train["stops"]:
        pair = []
        for key in ("arr", "dep"):
            text = stop.get(key)
            if text is None:
                pair.append(None)
                continue
            h, m = map(int, text.split(":"))
            minutes = h * 60 + m
            if minutes < last:
                day += 1
            last = minutes
            pair.append(base + timedelta(days=day, minutes=minutes))
        out.append((pair[0], pair[1]))
    return out


def simulate(network: dict, dates: list[date], rng: np.random.Generator) -> list[list[str]]:
    coords = {s["code"]: (s["lat"], s["lon"]) for s in network["stations"]}
    # One fog and one monsoon intensity per calendar day, shared by every train.
    span = [
        HISTORY_START + timedelta(days=i) for i in range((LIVE_DATES[-1] - HISTORY_START).days + 3)
    ]
    fog_i = {d: float(rng.beta(2.2, 1.6)) for d in span}
    rain_i = {d: float(rng.beta(2.0, 2.0)) for d in span}

    rows: list[list[str]] = []
    for run_date in dates:
        for train in network["trains"]:
            number = train["number"]
            kind = train["kind"]
            stops = [s["station"] for s in train["stops"]]
            sched = timetable(train, run_date)

            reliable = number == RELIABLE
            chronic = number == CHRONIC
            if reliable:
                dep_delay = 0 if rng.random() < 0.95 else int(rng.integers(1, 4))
            else:
                dep_delay = 0 if rng.random() < 0.65 else int(round(rng.exponential(5)))
            if chronic:
                dep_delay += int(round(rng.gamma(2.0, 12.0)))

            arr_delays: list[int | None] = [None]
            dep_delays: list[int | None] = [dep_delay]
            for i in range(1, len(stops)):
                prev, here = stops[i - 1], stops[i]
                sched_arr = sched[i][0]
                assert sched_arr is not None
                day = sched_arr.date()
                km = haversine_km(coords[prev], coords[here])
                last = i == len(stops) - 1

                if reliable:
                    added = rng.normal(0.0, 1.0)
                else:
                    added = rng.normal(0.8, 3.0)
                    if rng.random() < 0.015:
                        added += rng.exponential(40.0)
                if chronic:
                    added += rng.gamma(2.0, 3.5)

                if prev in FOG_WEIGHTS and here in FOG_WEIGHTS:
                    weight = (FOG_WEIGHTS[prev] + FOG_WEIGHTS[here]) / 2
                    scale = fog_scale(day) * fog_i[day] * fog_hour_factor(sched_arr.hour)
                    if scale > 0:
                        added += FOG_RATE * km / 100 * weight * scale * rng.lognormal(0.0, 0.35)
                if prev in MONSOON_WEIGHTS or here in MONSOON_WEIGHTS:
                    weight = (MONSOON_WEIGHTS.get(prev, 0.0) + MONSOON_WEIGHTS.get(here, 0.0)) / 2
                    scale = monsoon_scale(day) * rain_i[day]
                    if scale > 0:
                        added += MONSOON_RATE * km / 100 * weight * scale * rng.lognormal(0.0, 0.35)
                if here == JUNCTION:
                    added += rng.gamma(2.0, 2.0)
                    if JUNCTION_HOURS[0] <= sched_arr.hour < JUNCTION_HOURS[1]:
                        added += rng.gamma(3.0, 12.0)
                if (
                    run_date.isoformat() == INCIDENT["run_date"]
                    and number == INCIDENT["train"]
                    and here == INCIDENT["station"]
                ):
                    added += INCIDENT["added_min"]

                carried = dep_delays[-1] or 0
                if last and kind != "chair_car":
                    added -= min(0.25 * max(carried, 0), 12.0)  # recovery allowance
                arrival = int(round(carried + added))
                arrival = max(arrival, -5 if last else -2)
                arr_delays.append(arrival)
                if last:
                    dep_delays.append(None)
                else:
                    extra = rng.exponential(0.3 if reliable else 0.8)
                    dep_delays.append(int(round(max(arrival, 0) + extra)))

            for seq, code in enumerate(stops):
                sa, sd = sched[seq]
                aa = None if sa is None else sa + timedelta(minutes=arr_delays[seq] or 0)
                ad = None if sd is None else sd + timedelta(minutes=dep_delays[seq] or 0)
                # Real feeds have gaps: drop a few observed times (never the whole run).
                if aa is not None and seq > 0 and rng.random() < 0.003:
                    aa = None
                rows.append(
                    [
                        run_date.isoformat(),
                        number,
                        str(seq),
                        code,
                        _fmt(sa),
                        _fmt(aa),
                        _fmt(sd),
                        _fmt(ad),
                    ]
                )
    return rows


def _fmt(value: datetime | None) -> str:
    return "" if value is None else value.strftime("%Y-%m-%d %H:%M")


def main() -> None:
    network = json.loads(NETWORK.read_text("utf-8"))
    rng = np.random.default_rng(SEED)
    days = (HISTORY_END - HISTORY_START).days + 1
    history_dates = [HISTORY_START + timedelta(days=i) for i in range(days)]
    rows = simulate(network, history_dates + LIVE_DATES, rng)
    live = {d.isoformat() for d in LIVE_DATES}
    history = [r for r in rows if r[0] not in live]
    replay = [r for r in rows if r[0] in live]

    SAMPLES.mkdir(exist_ok=True)
    # mtime=0 keeps the gzip bytes identical between runs.
    with (
        open(SAMPLES / "history.csv.gz", "wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
    ):
        text = _csv([COLUMNS, *history])
        gz.write(text.encode("utf-8"))
    (SAMPLES / "live_replay.csv").write_text(_csv([COLUMNS, *replay]), encoding="utf-8")

    truth = {
        "_note": "Written by server/scripts/make_samples.py. Everything here was planted in "
        "simulated data; none of it describes real trains.",
        "history": {"start": HISTORY_START.isoformat(), "end": HISTORY_END.isoformat()},
        "live_dates": sorted(live),
        "on_time_minutes": 15,
        "fog": {
            "months": [12, 1],
            # Heavy fog sections: big enough to clear the reporting bar in analysis.json.
            "stations": [s for s, w in FOG_WEIGHTS.items() if w >= 0.8],
            # Light fog on short sections (NDLS-GZB is ~30 km): planted, but a few minutes only.
            "light_stations": [s for s, w in FOG_WEIGHTS.items() if w < 0.8],
            "rate_min_per_100km": FOG_RATE,
            "worst_hours": "21:00-10:00",
        },
        "monsoon": {
            "months": [7, 8],
            "stations": list(MONSOON_WEIGHTS),
            "rate_min_per_100km": MONSOON_RATE,
        },
        "junction_window": {
            "station": JUNCTION,
            "hours": list(JUNCTION_HOURS),
            "mean_added_min": 36,
        },
        "top_added_station": JUNCTION,
        # Downstream of the DDU window and the fog stretch: late on arrival, little added.
        "inherits_most": ["BXR", "ARA", "PNBE", "JSME", "ASN", "BWN", "HWH", "GAYA", "DHN"],
        "chronically_late_train": CHRONIC,
        "reliable_train": RELIABLE,
        "unusual_today": [INCIDENT],
        "model": {"p90_coverage_band": [0.82, 0.96]},
    }
    (SAMPLES / "ground_truth.json").write_text(json.dumps(truth, indent=2) + "\n", "utf-8")
    print(f"history: {len(history):,} rows, live replay: {len(replay):,} rows -> {SAMPLES}")


def _csv(rows: list[list[str]]) -> str:
    import io

    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


if __name__ == "__main__":
    main()
