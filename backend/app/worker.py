"""Single background thread that processes runs one at a time, in upload order (A47).

Duplicate checks and PO balances depend on earlier runs, so two runs must never be decided at the
same time. Uploads queue as QUEUED and are picked up in order.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Run
from app.pipeline.events import EventBus
from app.pipeline.runner import process_run
from app.schemas import RunStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Job:
    run_id: str
    force_extract: bool


class RunWorker:
    def __init__(self, session_maker: sessionmaker[Session], bus: EventBus, settings: Settings) -> None:
        self._sessions = session_maker
        self._bus = bus
        self._settings = settings
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="run-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout)
            self._thread = None

    def submit(self, run_id: str, force_extract: bool = False) -> None:
        self._queue.put(_Job(run_id, force_extract))

    @property
    def busy(self) -> bool:
        return self._queue.unfinished_tasks > 0

    def wait_idle(self) -> None:
        """Block until every submitted run has finished (used by tests and reset)."""
        self._queue.join()

    def recover(self) -> int:
        """After a restart: re-queue QUEUED runs, mark half-finished RUNNING runs as ERROR."""
        with self._sessions() as s:
            requeued = 0
            for run in s.scalars(select(Run).where(Run.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
                                 .order_by(Run.created_at)):
                if run.status == RunStatus.RUNNING:
                    run.status = RunStatus.ERROR
                    run.error = "Interrupted by a server restart; upload the file again"
                else:
                    self.submit(run.id)
                    requeued += 1
            s.commit()
        return requeued

    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                with self._sessions() as session:
                    process_run(session, job.run_id, bus=self._bus, settings=self._settings,
                                force_extract=job.force_extract)
            except Exception:  # process_run already turns stage errors into ERROR runs; this is a last guard
                log.exception("run %s failed outside the pipeline", job.run_id if job else None)
                if job is not None:
                    self._mark_error(job.run_id)
            finally:
                self._queue.task_done()

    def _mark_error(self, run_id: str) -> None:
        with self._sessions() as s:
            run = s.get(Run, run_id)
            if run is not None and run.status != RunStatus.DONE:
                run.status = RunStatus.ERROR
                run.error = run.error or "Internal error while processing"
                s.commit()
