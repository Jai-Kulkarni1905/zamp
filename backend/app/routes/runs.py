"""Runs: upload, list, detail, live events (SSE), original PDF, human review."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api_schemas import ReviewIn, RunCreated, RunDetail, RunList
from app.config import IST, MAX_UPLOAD_BYTES, Settings
from app.deps import get_app_settings, get_bus, get_session, get_sessions, get_worker
from app.models import Run, StageEvent
from app.pipeline.events import EventBus
from app.pipeline.runner import create_run, load_pdf
from app.routes._common import detail, summary, vendor_names
from app.schemas import Decision, Flag, RunStatus, Stage, StageEventOut, StageStatus
from app.worker import RunWorker

router = APIRouter(prefix="/api/runs", tags=["runs"])

KEEPALIVE_S = 15.0
TERMINAL = {RunStatus.DONE.value, RunStatus.ERROR.value}


def _get_run(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


@router.post("", status_code=201, response_model=RunCreated)
async def upload_run(
    file: UploadFile,
    force_extract: bool = False,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    worker: RunWorker = Depends(get_worker),
) -> RunCreated:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if b"%PDF-" not in data[:1024]:
        raise HTTPException(400, "Not a PDF file")
    if force_extract and settings.llm_mode != "live":
        raise HTTPException(400, "force_extract needs LLM_MODE=live (it makes a real Gemini call)")
    filename = Path(file.filename or "upload.pdf").name
    run = create_run(session, filename, data, settings)
    worker.submit(run.id, force_extract)
    return RunCreated(run_id=run.id, status=run.status, events_url=f"/api/runs/{run.id}/events",
                      detail_url=f"/api/runs/{run.id}")


@router.get("", response_model=RunList)
def list_runs(
    decision: Decision | None = Query(None, description="Automated decision"),
    status: RunStatus | None = None,
    vendor_id: str | None = None,
    flag: Flag | None = None,
    review_queue: bool = Query(False, description="Only NEEDS_REVIEW runs with no reviewer action"),
    date_from: date | None = Query(None, description="Processed on or after (IST)"),
    date_to: date | None = Query(None, description="Processed on or before (IST)"),
    q: str | None = Query(None, description="Search filename, invoice number, vendor"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> RunList:
    query = select(Run).order_by(Run.created_at.desc())
    if decision:
        query = query.where(Run.decision == decision.value)
    if status:
        query = query.where(Run.status == status.value)
    if vendor_id:
        query = query.where(Run.vendor_id == vendor_id)
    if review_queue:
        query = query.where(Run.decision == Decision.NEEDS_REVIEW.value, Run.reviewer_action.is_(None))
    names = vendor_names(session)
    items = [summary(r, names) for r in session.scalars(query)]
    # JSON flags, IST dates and free-text search are filtered here: the run table is small (A50).
    if flag:
        items = [i for i in items if flag.value in i.flags]
    if date_from:
        items = [i for i in items if i.created_at.astimezone(IST).date() >= date_from]
    if date_to:
        items = [i for i in items if i.created_at.astimezone(IST).date() <= date_to]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in " ".join(
            filter(None, [i.filename, i.invoice_number, i.vendor_name, i.matched_po])).lower()]
    return RunList(items=items[offset:offset + limit], total=len(items), limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunDetail:
    return detail(session, _get_run(session, run_id))


@router.get("/{run_id}/file")
def get_file(run_id: str, session: Session = Depends(get_session)) -> Response:
    run = _get_run(session, run_id)
    try:
        content = load_pdf(session, run)
    except OSError:
        raise HTTPException(404, "Original file is no longer stored") from None
    safe_name = run.filename.replace('"', "")
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{safe_name}"', "Cache-Control": "private, max-age=3600"})


@router.post("/{run_id}/review", response_model=RunDetail)
def review_run(run_id: str, body: ReviewIn, session: Session = Depends(get_session)) -> RunDetail:
    run = _get_run(session, run_id)
    if run.status != RunStatus.DONE:
        raise HTTPException(409, f"Run is {run.status}; only finished runs can be reviewed")
    if run.reviewer_action is not None:
        raise HTTPException(409, f"Run was already reviewed ({run.reviewer_action}); overrides are final (A48)")
    run.reviewer_action = body.action
    run.reviewer_note = body.note
    run.reviewed_at = datetime.now(timezone.utc)
    session.commit()
    return detail(session, run)


# -- Server-Sent Events -------------------------------------------------------


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {data}\n\n"


def _event_json(ev: StageEventOut) -> str:
    return ev.model_dump_json()


def _is_last(ev: StageEventOut) -> bool:
    """Explain is the final stage; its non-RUNNING event (PASS, FAIL or SKIPPED) closes the run's stream."""
    return ev.stage == Stage.EXPLAIN and ev.status != StageStatus.RUNNING


def _stored_events(sessions: sessionmaker[Session], run_id: str, after: int) -> tuple[list[StageEventOut], str]:
    with sessions() as s:
        run = s.get(Run, run_id)
        rows = s.scalars(select(StageEvent).where(StageEvent.run_id == run_id, StageEvent.seq > after)
                         .order_by(StageEvent.seq)).all()
        events = [StageEventOut(run_id=r.run_id, seq=r.seq, stage=Stage(r.stage), status=StageStatus(r.status),
                                message=r.message, started_at=r.started_at, ended_at=r.ended_at,
                                payload=r.payload_json or {}) for r in rows]
        return events, run.status if run else RunStatus.ERROR.value


def _final(sessions: sessionmaker[Session], run_id: str, wait_s: float = 5.0) -> dict[str, object]:
    """The last stage event is committed just before the run row; give it a moment to land."""
    deadline = time.monotonic() + wait_s
    while True:
        with sessions() as s:
            run = s.get(Run, run_id)
            if run is None or run.status in TERMINAL or time.monotonic() > deadline:
                return {"run_id": run_id, "status": run.status if run else None,
                        "decision": run.decision if run else None, "flags": list(run.flags or []) if run else []}
        time.sleep(0.05)


@router.get("/{run_id}/events", response_class=StreamingResponse)
async def run_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(None),
    sessions: sessionmaker[Session] = Depends(get_sessions),
    bus: EventBus = Depends(get_bus),
) -> StreamingResponse:
    """Replays stored events, then streams live ones. Ends with an `end` event when the run is DONE or ERROR."""
    with sessions() as s:
        _get_run(s, run_id)
    try:
        start = int(last_event_id or 0)
    except ValueError:
        start = 0

    async def stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StageEventOut] = asyncio.Queue()
        # Subscribe before replaying so nothing published in between is lost; seq numbers dedupe.
        unsubscribe = bus.subscribe(lambda e: loop.call_soon_threadsafe(queue.put_nowait, e), run_id)
        last = start
        try:
            stored, status = await asyncio.to_thread(_stored_events, sessions, run_id, last)
            finished = status in TERMINAL
            for ev in stored:
                yield _sse("stage", _event_json(ev), ev.seq)
                last = ev.seq
                finished = finished or _is_last(ev)
            while not finished:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
                except TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": keep-alive\n\n"
                    stored, status = await asyncio.to_thread(_stored_events, sessions, run_id, last)
                    finished = status in TERMINAL
                    for missed in stored:
                        yield _sse("stage", _event_json(missed), missed.seq)
                        last = missed.seq
                        finished = finished or _is_last(missed)
                    continue
                if ev.seq <= last:
                    continue
                yield _sse("stage", _event_json(ev), ev.seq)
                last = ev.seq
                finished = _is_last(ev)
            final = await asyncio.to_thread(_final, sessions, run_id)
            yield _sse("end", json.dumps(final))
        finally:
            unsubscribe()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
