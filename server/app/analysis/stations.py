"""Which stations cause delay, separated from the ones that only inherit it.

For every station: mean arrival delay (what a dashboard would rank by), mean inherited
delay (what trains bring in) and mean added delay (what the approach to the station adds),
with a 95% interval for the added mean.

The interval is a **cluster bootstrap by date**: whole days are resampled, not single
arrivals, because delays on one day are correlated (a foggy night slows every train).
Resampling single arrivals would pretend there are far more independent observations than
there are, and make the interval too narrow.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis.dataset import arrivals, quantile
from app.core.catalog import AnalysisConfig, Network
from app.schemas.analysis import Fact, StationReport, StationStat, fact

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_label(months: list[int]) -> str:
    """[12, 1] -> "Dec, Jan": calendar order, starting after the largest gap."""
    if not months:
        return "all year"
    ordered = sorted(set(months))
    gaps = [(ordered[(i + 1) % len(ordered)] - m) % 12 for i, m in enumerate(ordered)]
    start = (gaps.index(max(gaps)) + 1) % len(ordered)
    ordered = ordered[start:] + ordered[:start]
    return ", ".join(MONTHS[m - 1] for m in ordered)


def cluster_bootstrap_ci(
    values: pd.Series, clusters: pd.Series, reps: int, rng: np.random.Generator
) -> tuple[float, float]:
    """95% percentile interval of the mean, resampling whole clusters (days)."""
    grouped = pd.DataFrame({"v": values.to_numpy(), "c": clusters.to_numpy()}).groupby("c")["v"]
    sums = grouped.sum().to_numpy()
    counts = grouped.count().to_numpy()
    if len(sums) < 2:
        mean = float(values.mean())
        return mean, mean
    picks = rng.integers(0, len(sums), size=(reps, len(sums)))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def station_profile(
    stops: pd.DataFrame,
    network: Network,
    config: AnalysisConfig,
    months: list[int] | None = None,
    seed: int = 0,
) -> StationReport:
    """Rank stations by the delay they add (optionally within some months)."""
    rng = np.random.default_rng(seed)
    rows = arrivals(stops)
    if months:
        rows = rows[rows["month"].isin(months)]
    stats: list[StationStat] = []
    for code, group in rows.groupby("station"):
        if len(group) < config.min_rows_per_station:
            continue
        low, high = cluster_bootstrap_ci(
            group["added"], group["run_date"], config.bootstrap_reps, rng
        )
        arrival = float(group["arr_delay"].mean())
        added = float(group["added"].mean())
        station = network.by_code.get(str(code))
        stats.append(
            StationStat(
                code=str(code),
                name=station.name if station else str(code),
                n=len(group),
                arrival_mean=arrival,
                inherited_mean=float(group["inherited"].mean()),
                added_mean=added,
                added_ci_low=low,
                added_ci_high=high,
                added_p90=quantile(group["added"], 0.9),
                added_share=min(max(added / arrival, 0.0), 1.0) if arrival >= 1 else None,
                rank=0,
            )
        )
    stats.sort(key=lambda s: -s.added_mean)
    for rank, stat in enumerate(stats, start=1):
        stat.rank = rank
    naive_top = max(stats, key=lambda s: s.arrival_mean).code if stats else ""
    return StationReport(
        months=sorted(months or []),
        stations=stats,
        naive_top=naive_top,
        facts=_facts(stats, naive_top, months or [], config.hotspot_top_n),
    )


def _facts(stats: list[StationStat], naive_top: str, months: list[int], top_n: int) -> list[Fact]:
    period = month_label(months)
    facts = [fact("hotspots.period", "Period the ranking covers", period)]
    for stat in stats[:top_n]:
        prefix = f"hotspots.{stat.rank}"
        facts += [
            fact(f"{prefix}.station", f"#{stat.rank} station by added delay", stat.code),
            fact(f"{prefix}.name", f"#{stat.rank} station name", stat.name),
            fact(
                f"{prefix}.added",
                f"Mean delay added approaching {stat.code}",
                stat.added_mean,
                "min",
            ),
            fact(f"{prefix}.ci_low", f"95% interval low, {stat.code}", stat.added_ci_low, "min"),
            fact(f"{prefix}.ci_high", f"95% interval high, {stat.code}", stat.added_ci_high, "min"),
            fact(
                f"{prefix}.arrival", f"Mean arrival delay at {stat.code}", stat.arrival_mean, "min"
            ),
        ]
    by_code = {s.code: s for s in stats}
    if naive_top in by_code:
        naive = by_code[naive_top]
        facts += [
            fact("hotspots.naive_top", "Station with the worst mean arrival delay", naive.code),
            fact(
                "hotspots.naive_top.arrival",
                f"Mean arrival delay at {naive.code}",
                naive.arrival_mean,
                "min",
            ),
            fact(
                "hotspots.naive_top.added",
                f"Of which added approaching {naive.code}",
                naive.added_mean,
                "min",
            ),
            fact(
                "hotspots.naive_top.inherited",
                f"Inherited on arrival at {naive.code}",
                naive.inherited_mean,
                "min",
            ),
        ]
    return facts
