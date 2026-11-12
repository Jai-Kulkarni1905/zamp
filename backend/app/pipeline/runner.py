"""Orchestrates the 10 stages for one run and emits RUNNING then PASS/WARN/FAIL/SKIPPED per stage."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import repo
from app.config import Settings, get_settings
from app.llm.gemini import ExtractionResult, LLMError, extract_invoice
from app.models import RuleResultRow, Run
from app.pipeline.events import EventBus, record_event
from app.pipeline.stages.decide import decide
from app.pipeline.stages.duplicates import check_duplicates
from app.pipeline.stages.explain import explain
from app.pipeline.stages.extract import extract_failed, extract_ok
from app.pipeline.stages.ingest import IngestData, ingest, sha256
from app.pipeline.stages.normalize import normalize
from app.pipeline.stages.po_match import POMatch, check_amount, match_po
from app.pipeline.stages.validate import validate
from app.pipeline.stages.vendor import VendorMatch, check_vendor, vendor_key
from app.schemas import (
    STAGE_ORDER,
    DecisionResult,
    Explanation,
    NormalizedInvoice,
    RuleResult,
    RunStatus,
    Stage,
    StageResult,
    StageStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, filename: str, pdf_bytes: bytes, settings: Settings | None = None) -> Run:
    """Store the upload under data/uploads/<sha256>.pdf and create a QUEUED run."""
    settings = settings or get_settings()
    file_hash = sha256(pdf_bytes)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    path = settings.uploads_dir / f"{file_hash}.pdf"
    if not path.exists():
        path.write_bytes(pdf_bytes)
    run = Run(id=str(uuid.uuid4()), file_hash=file_hash, filename=filename, file_path=str(path),
              status=RunStatus.QUEUED, flags=[], created_at=_now())
    session.add(run)
    session.commit()
    return run


class _StageFailure(Exception):
    """A stage could not complete; the run ends as ERROR."""


@dataclass
class _State:
    """Data handed from one stage to the next."""

    ingest: IngestData | None = None
    extraction: ExtractionResult | None = None
    inv: NormalizedInvoice | None = None
    vendor: VendorMatch | None = None
    po: POMatch | None = None
    vendor_key: str | None = None
    decision: DecisionResult | None = None
    explanation: Explanation | None = None
    rules: list[RuleResult] = field(default_factory=list)


class _Pipeline:
    def __init__(self, session: Session, bus: EventBus, run: Run) -> None:
        self.session = session
        self.bus = bus
        self.run = run
        self.seq = 0
        self.state = _State()

    def emit(self, stage: Stage, status: StageStatus, message: str, started: datetime,
             ended: datetime | None, payload: dict[str, object] | None = None) -> None:
        self.seq += 1
        record_event(self.session, self.bus, run_id=self.run.id, seq=self.seq, stage=stage, status=status,
                     message=message, started_at=started, ended_at=ended, payload=payload)

    def stage(self, stage: Stage, fn: Callable[[], StageResult]) -> StageResult:
        started = _now()
        self.emit(stage, StageStatus.RUNNING, f"{stage.value} running", started, None)
        try:
            result = fn()
        except _StageFailure:
            raise
        except Exception as exc:  # an unexpected stage error ends the run cleanly, never a crash
            self.emit(stage, StageStatus.FAIL, f"Internal error: {exc}", started, _now(), {"error": repr(exc)})
            raise _StageFailure(f"{stage.value}: {exc}") from exc
        ended = _now()
        payload = dict(result.payload)
        payload["duration_ms"] = int((ended - started).total_seconds() * 1000)
        for r in result.rules:
            self.session.add(RuleResultRow(
                run_id=self.run.id, stage=r.stage.value, rule_id=r.rule_id, outcome=r.outcome.value,
                severity=r.severity.value, review_reason=r.review_reason, flag=r.flag.value if r.flag else None,
                message=r.message, evidence_json=r.model_dump(mode="json")["evidence"],
            ))
        self.state.rules.extend(result.rules)
        self.emit(stage, result.status, result.message, started, ended, payload)
        return result

    def skip_rest(self, after: Stage, reason: str) -> None:
        for s in STAGE_ORDER[STAGE_ORDER.index(after) + 1:]:
            t = _now()
            self.emit(s, StageStatus.SKIPPED, reason, t, t)

    # -- stage steps -------------------------------------------------------

    def do_ingest(self, pdf_bytes: bytes) -> StageResult:
        seen = repo.hash_seen_before(self.session, sha256(pdf_bytes), self.run.id)
        res, self.state.ingest = ingest(pdf_bytes, self.run.filename, seen)
        return res

    def do_extract(self, pdf_bytes: bytes, settings: Settings, force: bool) -> None:
        assert self.state.ingest is not None
        started = _now()
        self.emit(Stage.EXTRACT, StageStatus.RUNNING, "Reading the invoice", started, None)
        try:
            ext = extract_invoice(pdf_bytes, self.state.ingest.file_hash, filename=self.run.filename,
                                  force=force, settings=settings)
        except Exception as exc:  # LLMError, or anything unexpected: fail the stage, never crash
            err = exc if isinstance(exc, LLMError) else LLMError("failed", f"Extraction error: {exc}")
            res = extract_failed(err)
            self.emit(Stage.EXTRACT, res.status, res.message, started, _now(), res.payload)
            raise _StageFailure(err.message) from exc
        res = extract_ok(ext)
        ended = _now()
        payload = {**res.payload, "duration_ms": int((ended - started).total_seconds() * 1000)}
        self.emit(Stage.EXTRACT, res.status, res.message, started, ended, payload)
        self.state.extraction = ext
        self.run.extracted_json = ext.extraction.model_dump(mode="json")

    def do_normalize(self) -> StageResult:
        assert self.state.extraction is not None
        res, self.state.inv = normalize(self.state.extraction.extraction)
        return res

    def do_validate(self, today: date) -> StageResult:
        assert self.state.inv is not None and self.state.ingest is not None
        return validate(self.state.inv, is_scanned=self.state.ingest.is_scanned,
                        pdf_text=self.state.ingest.pdf_text, today=today)

    def do_vendor(self) -> StageResult:
        assert self.state.inv is not None
        res, self.state.vendor = check_vendor(self.state.inv, repo.load_vendors(self.session))
        self.state.vendor_key = vendor_key(self.state.inv, self.state.vendor)
        return res

    def do_po(self) -> StageResult:
        assert self.state.inv is not None
        pos = repo.load_pos(self.session, exclude_run_id=self.run.id)
        res, self.state.po = match_po(self.state.inv, self.state.vendor, pos)
        return res

    def do_amount(self) -> StageResult:
        assert self.state.inv is not None
        return check_amount(self.state.inv, self.state.po)

    def do_duplicates(self) -> StageResult:
        assert self.state.inv is not None and self.state.ingest is not None
        prior = repo.prior_runs(self.session, self.run.id)
        return check_duplicates(self.state.ingest.file_hash, self.state.inv, self.state.vendor_key, prior)

    def do_decide(self) -> StageResult:
        res, self.state.decision = decide(self.state.rules)
        return res

    def do_explain(self) -> StageResult:
        assert self.state.decision is not None and self.state.inv is not None
        res, self.state.explanation = explain(self.state.decision, self.state.rules, self.state.inv,
                                              self.state.vendor, self.state.po)
        return res

    def finish(self) -> None:
        s, run = self.state, self.run
        assert s.decision is not None and s.explanation is not None and s.inv is not None
        run.decision = s.decision.decision.value
        run.flags = [f.value for f in s.decision.flags]
        run.explanation_json = s.explanation.model_dump(mode="json")
        run.normalized_json = s.inv.model_dump(mode="json")
        run.matched_po = s.po.po.po_number if s.po else None
        run.po_match_type = s.po.match_type if s.po else None
        run.vendor_id = s.vendor.vendor.vendor_id if s.vendor else None
        run.vendor_key = s.vendor_key
        run.invoice_number = s.inv.invoice_number
        run.invoice_number_canonical = s.inv.invoice_number_canonical
        run.invoice_date = s.inv.invoice_date
        run.total = s.inv.total
        run.status = RunStatus.DONE


def process_run(
    session: Session,
    run_id: str,
    *,
    bus: EventBus,
    settings: Settings | None = None,
    today: date | None = None,
    force_extract: bool = False,
) -> Run:
    settings = settings or get_settings()
    today = today or settings.today()
    run = session.get(Run, run_id)
    if run is None:
        raise ValueError(f"run {run_id} not found")
    pdf_bytes = Path(run.file_path).read_bytes()
    run.status = RunStatus.RUNNING
    session.commit()
    p = _Pipeline(session, bus, run)
    t0 = time.perf_counter()

    steps: list[tuple[Stage, Callable[[], StageResult | None]]] = [
        (Stage.INGEST, lambda: p.stage(Stage.INGEST, lambda: p.do_ingest(pdf_bytes))),
        (Stage.EXTRACT, lambda: p.do_extract(pdf_bytes, settings, force_extract)),
        (Stage.NORMALIZE, lambda: p.stage(Stage.NORMALIZE, p.do_normalize)),
        (Stage.VALIDATE, lambda: p.stage(Stage.VALIDATE, lambda: p.do_validate(today))),
        (Stage.VENDOR, lambda: p.stage(Stage.VENDOR, p.do_vendor)),
        (Stage.PO_MATCH, lambda: p.stage(Stage.PO_MATCH, p.do_po)),
        (Stage.AMOUNT, lambda: p.stage(Stage.AMOUNT, p.do_amount)),
        (Stage.DUPLICATES, lambda: p.stage(Stage.DUPLICATES, p.do_duplicates)),
        (Stage.DECIDE, lambda: p.stage(Stage.DECIDE, p.do_decide)),
        (Stage.EXPLAIN, lambda: p.stage(Stage.EXPLAIN, p.do_explain)),
    ]
    current = Stage.INGEST
    try:
        for current, step in steps:
            step()
        p.finish()
    except _StageFailure as exc:
        p.skip_rest(current, "Skipped: an earlier stage failed")
        run.status = RunStatus.ERROR
        run.error = str(exc)
    except Exception as exc:  # outside any stage (DB, bookkeeping): still never leave a run RUNNING
        session.rollback()
        run = session.get(Run, run_id) or run
        run.status = RunStatus.ERROR
        run.error = f"Internal error: {exc}"
    run.duration_ms = int((time.perf_counter() - t0) * 1000)
    session.commit()
    return run
