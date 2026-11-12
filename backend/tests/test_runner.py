"""End to end through the runner with the real test PDFs and hand-built fixtures (no Gemini)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import repo
from app.config import Settings
from app.llm.gemini import fixture_path
from app.models import StageEvent
from app.pipeline.events import EventBus
from app.pipeline.runner import create_run, process_run
from app.pipeline.stages.ingest import sha256
from app.schemas import STAGE_ORDER, Extraction, StageEventOut
from tests.conftest import INVOICES
from tests.factories import EC1_A, EC1_B, EC1_C, EC2, EC3, EC4, HP2, make_extraction

SCENARIOS: dict[str, Extraction] = {
    "HP-1": make_extraction(), "HP-2": HP2, "EC-1-A": EC1_A, "EC-1-B": EC1_B, "EC-1-C": EC1_C,
    "EC-2": EC2, "EC-3": EC3, "EC-4": EC4,
}


def _write_fixtures(settings: Settings) -> None:
    for name, ex in SCENARIOS.items():
        h = sha256((INVOICES / f"{name}.pdf").read_bytes())
        path = fixture_path(h, settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"file_hash": h, "model": "hand-built", "extraction": ex.model_dump(mode="json")}))


def _run(session: Session, settings: Settings, name: str, bus: EventBus | None = None):  # type: ignore[no-untyped-def]
    pdf = INVOICES / f"{name}.pdf"
    run = create_run(session, pdf.name, pdf.read_bytes(), settings)
    return process_run(session, run.id, bus=bus or EventBus(), settings=settings)


def test_full_demo_order(session: Session, settings: Settings) -> None:
    """PLAN.md section 7, in demo order, from a fresh DB."""
    _write_fixtures(settings)
    expected = {
        "HP-1": ("APPROVED", []),
        "HP-2": ("APPROVED", []),
        "EC-1-A": ("APPROVED", []),
        "EC-1-B": ("APPROVED", []),
        "EC-1-C": ("NEEDS_REVIEW", ["OVER_PO"]),
        "EC-2": ("REJECTED", ["DUPLICATE"]),  # its PO overage is a consequence, not a flag (A42)
        "EC-3": ("NEEDS_REVIEW", ["PO_INFERRED", "LOW_CONFIDENCE"]),
        "EC-4": ("NEEDS_REVIEW", ["FRAUD_RISK"]),
    }
    runs = {}
    for name, (decision, flags) in expected.items():
        run = _run(session, settings, name)
        runs[name] = run
        assert run.status == "DONE", run.error
        assert (run.decision, run.flags) == (decision, flags), (name, run.explanation_json)

    assert "exceeds remaining ₹60,000.00 by ₹30,000.00" in runs["EC-1-C"].explanation_json["verdict"]
    assert runs["EC-2"].explanation_json["next_actions"] == ["Do not pay. Compare with the original run (HP-1.pdf)"]
    assert runs["EC-3"].matched_po == "PO-2026-0104" and runs["EC-3"].po_match_type == "INFERRED"
    assert any("invoice number" in a for a in runs["EC-3"].explanation_json["next_actions"])
    assert any("number on file (+91 40 6712 5500)" in a for a in runs["EC-4"].explanation_json["next_actions"])
    assert "Within tolerance" in " ".join(runs["HP-2"].explanation_json["why"])

    consumed = repo.consumed_by_po(session)
    assert consumed["PO-2026-0103"] == 240000  # A and B approved, C in review consumes nothing (A22)
    assert "PO-2026-0106" not in consumed


def test_reviewer_approval_consumes_balance(session: Session, settings: Settings) -> None:
    _write_fixtures(settings)
    run = _run(session, settings, "EC-4")
    assert run.decision == "NEEDS_REVIEW" and "PO-2026-0106" not in repo.consumed_by_po(session)
    run.reviewer_action = "APPROVE"
    session.commit()
    assert repo.consumed_by_po(session)["PO-2026-0106"] == 118000


def test_events_running_then_final_for_every_stage(session: Session, settings: Settings) -> None:
    _write_fixtures(settings)
    seen: list[StageEventOut] = []
    bus = EventBus()
    bus.subscribe(seen.append)
    run = _run(session, settings, "HP-1", bus)
    assert [e.stage for e in seen[0::2]] == STAGE_ORDER
    assert all(e.status == "RUNNING" for e in seen[0::2])
    assert all(e.status != "RUNNING" for e in seen[1::2])
    stored = session.scalars(select(StageEvent).where(StageEvent.run_id == run.id)).all()
    assert len(stored) == len(seen) == 20


def test_missing_fixture_ends_in_error_not_crash(session: Session, settings: Settings) -> None:
    run = _run(session, settings, "HP-1")  # no fixtures written
    assert run.status == "ERROR" and run.decision is None
    statuses = [e.status for e in session.scalars(select(StageEvent).where(StageEvent.run_id == run.id))]
    assert statuses[-1] == "SKIPPED" and "FAIL" in statuses


def test_resubmitting_same_file_is_duplicate(session: Session, settings: Settings) -> None:
    _write_fixtures(settings)
    assert _run(session, settings, "HP-1").decision == "APPROVED"
    second = _run(session, settings, "HP-1")
    assert second.decision == "REJECTED" and second.flags == ["DUPLICATE"]


def test_upload_stored_by_hash(session: Session, settings: Settings) -> None:
    _write_fixtures(settings)
    run = _run(session, settings, "HP-2")
    assert Path(run.file_path).name == f"{run.file_hash}.pdf" and Path(run.file_path).is_file()
