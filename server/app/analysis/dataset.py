"""Turn raw run rows into one tidy frame of stops with their delays.

The key columns, per arrival at a stop:

* ``arr_delay``: actual minus scheduled arrival. What a passenger on the platform sees.
* ``inherited``: the departure delay at the previous stop. Delay the train brought with it.
* ``added``: ``arr_delay - inherited``. Delay gained on the approach to this station: the
  section ending here (fog on the line, a congested junction, a slow block).

A station deep down the line can have a huge ``arr_delay`` and a near-zero ``added``: it is
not the problem, it inherits the problem. Ranking stations by ``added`` is what finds where
time is actually lost.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Engine, select

from app.core.catalog import Network
from app.db.models import RunStop

TIME_COLUMNS = ["sched_arr", "act_arr", "sched_dep", "act_dep"]
RAW_COLUMNS = ["run_date", "train_no", "seq", "station", *TIME_COLUMNS]


def read_history_csv(path: Path) -> pd.DataFrame:
    """Read a history export (``.csv`` or ``.csv.gz``) with the sample's columns."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        frame = pd.read_csv(handle, dtype={"train_no": str, "station": str})
    missing = [c for c in RAW_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {', '.join(missing)}")
    return parse_raw(frame)


def parse_raw(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce types: dates, times (IST, naive), integer sequence."""
    out = frame[RAW_COLUMNS].copy()
    out["run_date"] = pd.to_datetime(out["run_date"]).dt.normalize()
    for column in TIME_COLUMNS:
        out[column] = pd.to_datetime(out[column], errors="coerce")
    out["seq"] = out["seq"].astype(int)
    out["train_no"] = out["train_no"].astype(str)
    return out


def load_history(engine: Engine) -> pd.DataFrame:
    """Every history row in the database as a raw frame."""
    columns = [getattr(RunStop, name) for name in RAW_COLUMNS]
    with engine.connect() as connection:
        frame = pd.read_sql(select(*columns), connection)
    return parse_raw(frame)


def prepare(raw: pd.DataFrame, network: Network) -> pd.DataFrame:
    """Add delays, inherited and added delay, calendar fields and section length."""
    df = raw.sort_values(["train_no", "run_date", "seq"]).reset_index(drop=True)
    df["arr_delay"] = (df["act_arr"] - df["sched_arr"]).dt.total_seconds() / 60
    df["dep_delay"] = (df["act_dep"] - df["sched_dep"]).dt.total_seconds() / 60
    runs = df.groupby(["train_no", "run_date"], sort=False)
    df["prev_station"] = runs["station"].shift(1)
    df["inherited"] = runs["dep_delay"].shift(1)
    df["added"] = df["arr_delay"] - df["inherited"]
    when = df["sched_arr"].fillna(df["sched_dep"])
    df["month"] = when.dt.month.astype(int)
    df["hour"] = when.dt.hour.astype(int)
    df["is_last"] = df["seq"] == runs["seq"].transform("max")
    km = {
        (a, b): network.segment_km(a, b)
        for a, b in df[["prev_station", "station"]].dropna().drop_duplicates().itertuples(False)
    }
    df["km"] = [
        km.get((a, b), 0.0) if isinstance(a, str) else 0.0
        for a, b in zip(df["prev_station"], df["station"], strict=True)
    ]
    return df


def arrivals(stops: pd.DataFrame) -> pd.DataFrame:
    """Rows where a train arrived from a previous stop and both delays are known."""
    mask = (stops["seq"] > 0) & stops["added"].notna()
    return stops.loc[mask]


def quantile(values: np.ndarray | pd.Series, q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q)) if len(values) else 0.0
