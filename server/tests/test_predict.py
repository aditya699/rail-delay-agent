"""The arrival-delay forecast: time-based hold-out, baseline, quantiles."""

from __future__ import annotations

from datetime import date

from app.container import Container


def test_forecast_beats_persistence_with_sane_coverage(seeded: Container, truth: dict) -> None:
    card = seeded.analytics.current.card
    assert card.test_end == date(2026, 11, 25)
    assert (card.test_end - card.test_start).days == 89
    assert card.mae_model < card.mae_persistence
    low, high = truth["model"]["p90_coverage_band"]
    assert low <= card.p90_coverage <= high
    # The further ahead, the more the baseline's error grows: the model's edge widens.
    first, last = card.by_horizon[0], card.by_horizon[-1]
    assert last.mae_persistence - last.mae_model > first.mae_persistence - first.mae_model


def test_forecast_covers_every_stop_ahead(seeded: Container) -> None:
    analytics = seeded.analytics.current
    train = seeded.catalog.network.train("22447")
    assert train is not None
    out = analytics.forecaster.forecast(train, date(2026, 11, 27), 3, 20)
    assert [f.seq for f in out] == list(range(4, len(train.stops)))
    assert all(f.p90_delay >= f.p50_delay for f in out)
    assert all(f.eta_p90 >= f.eta_p50 >= f.sched_arr for f in out if f.p50_delay >= 0)
    assert analytics.forecaster.forecast(train, date(2026, 11, 27), len(train.stops) - 1, 5) == []


def test_forecast_knows_about_the_evening_junction(seeded: Container) -> None:
    """22830 reaches DDU at 19:05, inside the planted window: expect delay to grow there."""
    forecaster = seeded.analytics.current.forecaster
    train = seeded.catalog.network.train("22830")
    assert train is not None
    gaya = train.seq("GAYA")
    assert gaya is not None
    ddu = next(
        f for f in forecaster.forecast(train, date(2026, 11, 27), gaya, 10) if f.station == "DDU"
    )
    assert ddu.p50_delay >= 10 + 20
