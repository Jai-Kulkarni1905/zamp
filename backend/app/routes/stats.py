"""Dashboard KPIs."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_schemas import Stats
from app.deps import get_session
from app.models import Run
from app.schemas import Decision, Flag, RunStatus

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=Stats)
def get_stats(session: Session = Depends(get_session)) -> Stats:
    runs = list(session.scalars(select(Run)))
    done = [r for r in runs if r.status == RunStatus.DONE]
    decisions = {d.value: sum(1 for r in done if r.decision == d) for d in Decision}
    effective = {d.value: sum(1 for r in done if r.effective_decision == d) for d in Decision}
    durations = [r.duration_ms for r in done if r.duration_ms is not None]
    zero = Decimal("0.00")
    return Stats(
        runs_total=len(runs),
        runs_done=len(done),
        runs_error=sum(1 for r in runs if r.status == RunStatus.ERROR),
        runs_in_progress=sum(1 for r in runs if r.status in (RunStatus.QUEUED, RunStatus.RUNNING)),
        decisions=decisions,
        effective_decisions=effective,
        approval_rate=round(decisions[Decision.APPROVED] / len(done), 4) if done else None,
        review_queue=sum(1 for r in done if r.decision == Decision.NEEDS_REVIEW and r.reviewer_action is None),
        avg_processing_ms=round(sum(durations) / len(durations)) if durations else None,
        value_processed=sum((r.total for r in done if r.total is not None), zero),
        value_approved=sum((r.total for r in done if r.total is not None
                            and r.effective_decision == Decision.APPROVED), zero),
        flags={f.value: sum(1 for r in done if f.value in (r.flags or [])) for f in Flag},
    )
