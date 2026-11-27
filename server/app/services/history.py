"""Load running history (scheduled and actual times per stop) into ``run_stops``."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.dataset import read_history_csv
from app.core.catalog import Network
from app.db.models import RunStop
from app.db.session import session_scope

logger = logging.getLogger(__name__)

HISTORY_FILE = "history.csv.gz"
CHUNK = 5000


class ImportReport(BaseModel):
    file: str
    inserted: int
    skipped_unknown: int
    runs: int
    first_date: str | None
    last_date: str | None


class HistoryService:
    def __init__(self, session_factory: sessionmaker[Session], network: Network) -> None:
        self.session_factory = session_factory
        self.network = network

    def count(self) -> int:
        with session_scope(self.session_factory) as session:
            return int(session.scalar(select(func.count(RunStop.id))) or 0)

    def seed_samples(self, samples_dir: Path) -> ImportReport:
        return self.import_file(samples_dir / HISTORY_FILE)

    def import_file(self, path: Path, *, replace: bool = False) -> ImportReport:
        """Import a history CSV. Rows for trains or stations not in network.json are skipped;
        a (train, date) already in the database is replaced only with ``replace=True``."""
        frame = read_history_csv(path)
        known = frame["train_no"].isin(self.network.by_number) & frame["station"].isin(
            self.network.by_code
        )
        skipped = int((~known).sum())
        frame = frame[known]
        records = _records(frame)
        with session_scope(self.session_factory) as session:
            existing = set(session.execute(select(RunStop.train_no, RunStop.run_date)).all())
            keys = {(r["train_no"], r["run_date"]) for r in records}
            clash = keys & existing
            if clash and replace:
                for train_no, run_date in clash:
                    session.execute(
                        delete(RunStop).where(
                            RunStop.train_no == train_no, RunStop.run_date == run_date
                        )
                    )
                clash = set()
            records = [r for r in records if (r["train_no"], r["run_date"]) not in clash]
            for start in range(0, len(records), CHUNK):
                session.execute(insert(RunStop), records[start : start + CHUNK])
        dates = sorted({r["run_date"] for r in records})
        report = ImportReport(
            file=path.name,
            inserted=len(records),
            skipped_unknown=skipped,
            runs=len({(r["train_no"], r["run_date"]) for r in records}),
            first_date=dates[0].isoformat() if dates else None,
            last_date=dates[-1].isoformat() if dates else None,
        )
        logger.info("Imported %s: %d rows, %d runs", path.name, report.inserted, report.runs)
        return report


def _records(frame: pd.DataFrame) -> list[dict]:
    def value(x: object) -> object:
        return None if pd.isna(x) else x.to_pydatetime()  # type: ignore[union-attr]

    out = []
    for row in frame.itertuples(index=False):
        out.append(
            {
                "run_date": row.run_date.date(),
                "train_no": row.train_no,
                "seq": int(row.seq),
                "station": row.station,
                "sched_arr": value(row.sched_arr),
                "act_arr": value(row.act_arr),
                "sched_dep": value(row.sched_dep),
                "act_dep": value(row.act_dep),
                "source": "history",
            }
        )
    return out
