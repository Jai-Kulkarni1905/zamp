"""Event bus: every StageEvent is persisted, then fanned out to live subscribers (SSE in Layer 3)."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import StageEvent
from app.schemas import Stage, StageEventOut, StageStatus

Subscriber = Callable[[StageEventOut], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str | None, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, callback: Subscriber, run_id: str | None = None) -> Callable[[], None]:
        """Subscribe to one run, or to every run when run_id is None. Returns an unsubscribe function."""
        with self._lock:
            self._subs[run_id].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subs[run_id]:
                    self._subs[run_id].remove(callback)

        return unsubscribe

    def publish(self, event: StageEventOut) -> None:
        with self._lock:
            targets = list(self._subs[event.run_id]) + list(self._subs[None])
        for cb in targets:
            cb(event)


def record_event(
    session: Session,
    bus: EventBus,
    *,
    run_id: str,
    seq: int,
    stage: Stage,
    status: StageStatus,
    message: str,
    started_at: datetime,
    ended_at: datetime | None,
    payload: dict[str, Any] | None = None,
) -> StageEventOut:
    event = StageEventOut(run_id=run_id, seq=seq, stage=stage, status=status, message=message,
                          started_at=started_at, ended_at=ended_at, payload=payload or {})
    session.add(StageEvent(run_id=run_id, seq=seq, stage=stage.value, status=status.value, message=message,
                           started_at=started_at, ended_at=ended_at,
                           payload_json=event.model_dump(mode="json")["payload"]))
    session.commit()
    bus.publish(event)
    return event
