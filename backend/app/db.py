"""Engine and session factory. SQLite locally, Postgres via DATABASE_URL, same code."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        if ":memory:" not in url:
            from pathlib import Path

            Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine:
    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine)
    return engine


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
