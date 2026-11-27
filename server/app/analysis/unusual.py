"""Is today's delay unusual for this train at this station?

A train that is always 60 minutes late at Patna being 60 minutes late is normal news; a
train that is usually on time at Ratnagiri being 80 minutes late is not. The rule compares
today's delay with the same train's recent history at the same stop and needs both:

* more than ``over_p90_min`` above its 90th percentile (worse than nine runs in ten), and
* more than ``over_median_min`` above its median (a big gap in minutes, not just in rank),

with at least ``min_runs`` runs of history. Both thresholds live in ``analysis.json``.
"""

from __future__ import annotations

from app.core.catalog import UnusualRule
from app.schemas.analysis import DelayStats


def is_unusual(delay_min: float, usual: DelayStats | None, rule: UnusualRule) -> bool:
    if usual is None or usual.n < rule.min_runs:
        return False
    return (
        delay_min >= usual.p90 + rule.over_p90_min
        and delay_min >= usual.median + rule.over_median_min
    )
