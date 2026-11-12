from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app import repo
from app.config import ROOT, Settings, get_settings
from app.db import make_engine, session_factory
from app.models import Base
from app.schemas import PORec, VendorRec
from app.seed import seed_master_data

TODAY = date(2026, 11, 12)  # the anchor date the test PDFs were generated against (A32)
INVOICES = ROOT / "data" / "invoices"


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as s:
        seed_master_data(s, ROOT / "data" / "seed")
        yield s


@pytest.fixture
def vendors(session: Session) -> list[VendorRec]:
    return repo.load_vendors(session)


@pytest.fixture
def pos(session: Session) -> dict[str, PORec]:
    return repo.load_pos(session)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Fixture mode only, with an isolated fixtures and uploads directory. Never calls Gemini."""
    return dataclasses.replace(get_settings(), llm_mode="fixture", fixtures_dir=tmp_path / "fixtures",
                               uploads_dir=tmp_path / "uploads", as_of_date=TODAY)
