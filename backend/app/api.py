"""App factory. Tests call create_app() with their own settings and engine; app/main.py builds the real one."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import Engine, func, select

from app.config import ROOT, Settings, get_settings
from app.db import make_engine, session_factory
from app.models import Base, Vendor
from app.pipeline.events import EventBus
from app.routes import admin, pos, runs, stats, vendors
from app.seed import seed_master_data
from app.worker import RunWorker


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    bus = EventBus()
    worker = RunWorker(sessions, bus, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        with sessions() as s:
            if not s.scalar(select(func.count()).select_from(Vendor)):
                seed_master_data(s, settings.seed_dir)
        worker.recover()
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Tally", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.bus = bus
    app.state.worker = worker
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["Content-Disposition"])
    for module in (runs, pos, vendors, stats, admin):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"ok": True, "llm_mode": settings.llm_mode, "worker_busy": worker.busy}

    mount_frontend(app, ROOT / "frontend" / "dist")
    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app from the same origin (one container). Unknown non-API paths get
    index.html so client routes like /run/:id survive a reload. No-op in dev, where Vite serves the UI."""
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    # HEAD too: uptime checkers and link-preview bots probe pages with HEAD before GET.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "Not found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            # Hashed build assets never change; index.html must always be revalidated.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if path.startswith("assets/"):
            raise HTTPException(404, "Not found")  # a missing bundle must not come back as HTML
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
