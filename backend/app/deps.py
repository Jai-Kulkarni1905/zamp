"""FastAPI dependencies shared by the routers. State is attached to the app in app/api.py."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.pipeline.events import EventBus
from app.worker import RunWorker


def get_session(request: Request) -> Iterator[Session]:
    maker: sessionmaker[Session] = request.app.state.sessions
    with maker() as session:
        yield session


def get_sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.sessions  # type: ignore[no-any-return]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_worker(request: Request) -> RunWorker:
    return request.app.state.worker  # type: ignore[no-any-return]


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus  # type: ignore[no-any-return]
