"""ORM models: the running history the analysis learns from, and the live feed's events.

All times are Indian Standard Time, stored without a zone (the railway's own clock).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class RunStop(Base):
    """One stop of one train's run: scheduled and actual times (history)."""

    __tablename__ = "run_stops"
    __table_args__ = (
        UniqueConstraint("train_no", "run_date", "seq", name="uq_run_stops"),
        Index("ix_run_stops_station", "station"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    train_no: Mapped[str] = mapped_column(String(8))
    seq: Mapped[int] = mapped_column(Integer)
    station: Mapped[str] = mapped_column(String(8))
    sched_arr: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    act_arr: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sched_dep: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    act_dep: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="history")


class LiveEvent(Base):
    """A train arrived at or departed from a stop, as reported by the live source."""

    __tablename__ = "live_events"
    __table_args__ = (
        UniqueConstraint("train_no", "run_date", "seq", "event", name="uq_live_events"),
        Index("ix_live_events_train", "train_no", "run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_no: Mapped[str] = mapped_column(String(8))
    run_date: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer)
    station: Mapped[str] = mapped_column(String(8))
    event: Mapped[str] = mapped_column(String(3))  # arr | dep
    scheduled: Mapped[datetime] = mapped_column(DateTime)
    actual: Mapped[datetime] = mapped_column(DateTime)
    delay_min: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # simulated | http
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
