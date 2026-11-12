"""Demo prep: wipe all runs and reseed vendors and POs."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api_schemas import ResetResult
from app.config import Settings
from app.deps import get_app_settings, get_session, get_worker
from app.seed import seed_master_data, wipe_runs
from app.worker import RunWorker

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset", response_model=ResetResult)
def reset(
    x_admin_token: str | None = Header(None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    worker: RunWorker = Depends(get_worker),
) -> ResetResult:
    if settings.admin_token and not hmac.compare_digest(x_admin_token or "", settings.admin_token):
        raise HTTPException(401, "Missing or wrong X-Admin-Token")
    if worker.busy:
        raise HTTPException(409, "A run is still being processed; try again in a moment")
    removed = wipe_runs(session)
    return ResetResult(runs_removed=removed, seeded=seed_master_data(session, settings.seed_dir))
