"""Forecast a train's arrival delay at each stop ahead, from where it is now.

**Question:** the train just left stop *k* with *d* minutes of delay. How late will it be at
stop *j*? One row per (run, k, j) pair in history; target = arrival delay at *j*.

**Features** (all known at prediction time):

* ``current_delay``: *d*. The single best predictor, because delay propagates.
* ``stops_ahead``, ``km_ahead``: how far there is to go (more noise, more room to recover).
* ``month``, ``target_hour``: calendar position of the arrival at *j*.
* ``exp_added_month``: the sum, over the stops between *k* and *j*, of each station's
  historical mean added delay in that month. Encodes "fog ahead" or "monsoon ahead".
* ``exp_added_hour``: the same by scheduled hour. Encodes "DDU at 19:00 ahead".
* ``train_added_per_stop``: this train's own mean added delay per stop (chronic lateness).
* ``is_terminal``: timetables pad the last section, so trains recover some delay there.

**Models:** gradient-boosted trees with a quantile loss (scikit-learn's
``HistGradientBoostingRegressor(loss="quantile")``), one for the median (p50) and one
for the 90th percentile (p90). The p50 is the ETA; p50-p90 is the band shown to the user.

**Evaluation:** a time-based split. The last ``test_days`` of history are held out, the
station/train profiles and the models are fitted on everything before, and the test
period is scored against the **persistence baseline** ("the delay stays what it is now").
A random split would leak: runs on the same foggy day would sit in both train and test.
After scoring, the profiles and models are refitted on all history for serving.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from app.analysis.dataset import arrivals
from app.core.catalog import AnalysisConfig, Network, Train
from app.schemas.analysis import HorizonScore, ModelCard, StopForecast, fact

logger = logging.getLogger(__name__)

FEATURES = [
    "current_delay",
    "stops_ahead",
    "km_ahead",
    "month",
    "target_hour",
    "exp_added_month",
    "exp_added_hour",
    "train_added_per_stop",
    "is_terminal",
]
QUANTILES = (0.5, 0.9)
HORIZONS = [("1 stop", 1, 1), ("2-3 stops", 2, 3), ("4-6 stops", 4, 6), ("7+ stops", 7, 99)]
KEYS = ["train_no", "run_date"]


@dataclass
class Profiles:
    """Historical mean added delay by station x month, station x hour, and per train."""

    station_month: dict[tuple[str, int], float] = field(default_factory=dict)
    station_hour: dict[tuple[str, int], float] = field(default_factory=dict)
    station: dict[str, float] = field(default_factory=dict)
    train: dict[str, float] = field(default_factory=dict)

    @classmethod
    def fit(cls, stops: pd.DataFrame) -> Profiles:
        rows = arrivals(stops)
        return cls(
            station_month=rows.groupby(["station", "month"])["added"].mean().to_dict(),
            station_hour=rows.groupby(["station", "hour"])["added"].mean().to_dict(),
            station=rows.groupby("station")["added"].mean().to_dict(),
            train=rows.groupby("train_no")["added"].mean().to_dict(),
        )

    def month_value(self, station: str, month: int) -> float:
        return self.station_month.get((station, month), self.station.get(station, 0.0))

    def hour_value(self, station: str, hour: int) -> float:
        return self.station_hour.get((station, hour), self.station.get(station, 0.0))


def build_pairs(stops: pd.DataFrame, profiles: Profiles) -> pd.DataFrame:
    """Every (run, from-stop k, to-stop j > k) pair with features and (if known) target."""
    s = stops.copy()
    arriving = s["seq"] > 0
    s["v_month"] = [
        profiles.month_value(st, m) if a else 0.0
        for st, m, a in zip(s["station"], s["month"], arriving, strict=True)
    ]
    s["v_hour"] = [
        profiles.hour_value(st, h) if a else 0.0
        for st, h, a in zip(s["station"], s["hour"], arriving, strict=True)
    ]
    runs = s.groupby(KEYS, sort=False)
    for column in ("v_month", "v_hour", "km"):
        s[f"cum_{column}"] = runs[column].cumsum()
    cums = ["cum_v_month", "cum_v_hour", "cum_km"]

    origins = s[s["dep_delay"].notna() & ~s["is_last"]][[*KEYS, "seq", "dep_delay", *cums]]
    targets = s[arriving][[*KEYS, "seq", "station", "arr_delay", "month", "hour", "is_last", *cums]]
    pairs = origins.merge(targets, on=KEYS, suffixes=("_k", "_j"))
    pairs = pairs[pairs["seq_j"] > pairs["seq_k"]].reset_index(drop=True)
    pairs["current_delay"] = pairs["dep_delay"]
    pairs["stops_ahead"] = pairs["seq_j"] - pairs["seq_k"]
    pairs["km_ahead"] = pairs["cum_km_j"] - pairs["cum_km_k"]
    pairs["target_hour"] = pairs["hour"]
    pairs["exp_added_month"] = pairs["cum_v_month_j"] - pairs["cum_v_month_k"]
    pairs["exp_added_hour"] = pairs["cum_v_hour_j"] - pairs["cum_v_hour_k"]
    pairs["train_added_per_stop"] = pairs["train_no"].map(profiles.train).fillna(0.0)
    pairs["is_terminal"] = pairs["is_last"].astype(int)
    return pairs


def _fit(pairs: pd.DataFrame, config: AnalysisConfig) -> dict[float, HistGradientBoostingRegressor]:
    cfg = config.model
    train = pairs[pairs["arr_delay"].notna()]
    if len(train) > cfg.max_train_rows:
        train = train.sample(cfg.max_train_rows, random_state=cfg.seed)
    models = {}
    for q in QUANTILES:
        model = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=q,
            max_iter=cfg.max_iter,
            learning_rate=cfg.learning_rate,
            max_leaf_nodes=cfg.max_leaf_nodes,
            random_state=cfg.seed,
        )
        model.fit(train[FEATURES].to_numpy(dtype=float), train["arr_delay"].to_numpy())
        models[q] = model
    return models


def _predict(
    models: dict[float, HistGradientBoostingRegressor], pairs: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    x = pairs[FEATURES].to_numpy(dtype=float)
    p50 = models[0.5].predict(x)
    p90 = np.maximum(models[0.9].predict(x), p50)  # quantiles must not cross
    return p50, p90


class DelayForecaster:
    def __init__(self, network: Network, config: AnalysisConfig) -> None:
        self.network = network
        self.config = config
        self.profiles = Profiles()
        self.models: dict[float, HistGradientBoostingRegressor] = {}
        self.card: ModelCard | None = None

    def fit(self, stops: pd.DataFrame) -> ModelCard:
        """Score on a time-based hold-out, then refit on all history for serving."""
        cfg = self.config.model
        as_of = stops["run_date"].max()
        test_start = as_of - timedelta(days=cfg.test_days - 1)
        last_train_day = test_start - timedelta(days=1)
        before = stops[stops["run_date"] < test_start]
        after = stops[stops["run_date"] >= test_start]

        profiles = Profiles.fit(before)
        train_pairs = build_pairs(before, profiles)
        models = _fit(train_pairs, self.config)
        test = build_pairs(after, profiles)
        test = test[test["arr_delay"].notna()].reset_index(drop=True)
        p50, p90 = _predict(models, test)
        y = test["arr_delay"].to_numpy()
        persistence = test["current_delay"].to_numpy()
        mae_model = float(np.mean(np.abs(y - p50)))
        mae_persistence = float(np.mean(np.abs(y - persistence)))
        coverage = float(np.mean(y <= p90))
        horizons = []
        for label, lo, hi in HORIZONS:
            mask = (test["stops_ahead"] >= lo) & (test["stops_ahead"] <= hi)
            if mask.any():
                horizons.append(
                    HorizonScore(
                        bucket=label,
                        n=int(mask.sum()),
                        mae_model=float(np.mean(np.abs(y[mask] - p50[mask]))),
                        mae_persistence=float(np.mean(np.abs(y[mask] - persistence[mask]))),
                    )
                )
        improvement = (1 - mae_model / mae_persistence) * 100 if mae_persistence else 0.0
        card = ModelCard(
            trained_on=f"{stops['run_date'].min().date()} to {last_train_day.date()}",
            test_start=test_start.date(),
            test_end=as_of.date(),
            n_train=int(min(len(train_pairs), cfg.max_train_rows)),
            n_test=len(test),
            features=FEATURES,
            mae_model=mae_model,
            mae_persistence=mae_persistence,
            mae_improvement_pct=improvement,
            p90_coverage=coverage,
            by_horizon=horizons,
            facts=[
                fact(
                    "model.mae", "Forecast mean absolute error on held-out days", mae_model, "min"
                ),
                fact(
                    "model.mae_persistence",
                    "Error of 'the delay stays the same'",
                    mae_persistence,
                    "min",
                ),
                fact("model.improvement_pct", "Error reduction vs that baseline", improvement, "%"),
                fact(
                    "model.p90_coverage",
                    "Share of held-out arrivals at or below the p90",
                    coverage * 100,
                    "%",
                ),
                fact("model.test_days", "Days held out for testing", cfg.test_days, "days"),
            ],
        )
        logger.info(
            "Forecast: MAE %.1f min vs persistence %.1f (%.0f%% better), p90 coverage %.0f%%",
            mae_model,
            mae_persistence,
            improvement,
            coverage * 100,
        )

        self.profiles = Profiles.fit(stops)
        self.models = _fit(build_pairs(stops, self.profiles), self.config)
        self.card = card
        return card

    def forecast(
        self, train: Train, run_date: date, from_seq: int, current_delay: float
    ) -> list[StopForecast]:
        """p50/p90 arrival delay at every stop after ``from_seq``, given the delay now."""
        if not self.models or from_seq >= len(train.stops) - 1:
            return []
        frame = timetable_frame(train, run_date, self.network)
        frame.loc[frame["seq"] == from_seq, "dep_delay"] = float(current_delay)
        pairs = build_pairs(frame, self.profiles)
        pairs = pairs[pairs["seq_k"] == from_seq].reset_index(drop=True)
        p50, p90 = _predict(self.models, pairs)
        out = []
        for row, mid, high in zip(pairs.itertuples(), p50, p90, strict=True):
            sched = frame.loc[frame["seq"] == row.seq_j, "sched_arr"].iloc[0].to_pydatetime()
            mid_i, high_i = int(round(mid)), int(round(high))
            out.append(
                StopForecast(
                    seq=int(row.seq_j),
                    station=str(row.station),
                    station_name=self.network.by_code[str(row.station)].name,
                    sched_arr=sched,
                    p50_delay=mid_i,
                    p90_delay=max(high_i, mid_i),
                    eta_p50=sched + timedelta(minutes=mid_i),
                    eta_p90=sched + timedelta(minutes=max(high_i, mid_i)),
                )
            )
        return out


def scheduled_times(train: Train, run_date: date) -> list[tuple[datetime | None, datetime | None]]:
    """(arrival, departure) for each stop of ``train`` on ``run_date``, rolling past midnight."""
    base = datetime(run_date.year, run_date.month, run_date.day)
    out: list[tuple[datetime | None, datetime | None]] = []
    day, last = 0, -1
    for stop in train.stops:
        pair: list[datetime | None] = []
        for text in (stop.arr, stop.dep):
            if text is None:
                pair.append(None)
                continue
            hours, minutes = map(int, text.split(":"))
            clock = hours * 60 + minutes
            if clock < last:
                day += 1
            last = clock
            pair.append(base + timedelta(days=day, minutes=clock))
        out.append((pair[0], pair[1]))
    return out


def timetable_frame(train: Train, run_date: date, network: Network) -> pd.DataFrame:
    """A run with only its timetable filled in, shaped like :func:`prepare`'s output."""
    times = scheduled_times(train, run_date)
    rows = []
    for seq, (stop, (arr, dep)) in enumerate(zip(train.stops, times, strict=True)):
        when = arr or dep
        assert when is not None
        prev = train.stops[seq - 1].station if seq else None
        rows.append(
            {
                "train_no": train.number,
                "run_date": pd.Timestamp(run_date),
                "seq": seq,
                "station": stop.station,
                "sched_arr": pd.Timestamp(arr) if arr else pd.NaT,
                "arr_delay": np.nan,
                "dep_delay": np.nan,
                "month": when.month,
                "hour": when.hour,
                "is_last": seq == len(train.stops) - 1,
                "km": network.segment_km(prev, stop.station) if prev else 0.0,
            }
        )
    return pd.DataFrame(rows)
