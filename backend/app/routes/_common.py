"""Builders that turn DB rows into API views. Shared by the routers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import repo
from app.api_schemas import POBalance, RuleView, RunDetail, RunSummary, StageView
from app.models import PurchaseOrder, Run, Vendor
from app.schemas import STAGE_ORDER


def vendor_names(session: Session) -> dict[str, str]:
    return {v.vendor_id: v.legal_name for v in session.scalars(select(Vendor))}


def summary(run: Run, names: dict[str, str]) -> RunSummary:
    return RunSummary(
        id=run.id, filename=run.filename, status=run.status, decision=run.decision,
        effective_decision=run.effective_decision, flags=list(run.flags or []), vendor_id=run.vendor_id,
        vendor_name=names.get(run.vendor_id or ""), invoice_number=run.invoice_number,
        invoice_date=run.invoice_date, total=run.total, matched_po=run.matched_po,
        po_match_type=run.po_match_type, created_at=run.created_at, duration_ms=run.duration_ms,
        reviewer_action=run.reviewer_action,
        verdict=(run.explanation_json or {}).get("verdict"),
    )


def po_balances(session: Session) -> dict[str, POBalance]:
    consumed = repo.consumed_by_po(session)
    names = vendor_names(session)
    out: dict[str, POBalance] = {}
    for po in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.po_number)):
        used = consumed.get(po.po_number, po.total_amount * 0)
        out[po.po_number] = POBalance(
            po_number=po.po_number, vendor_id=po.vendor_id, vendor_name=names.get(po.vendor_id),
            status=po.status, issue_date=po.issue_date, total=po.total_amount, consumed=used,
            remaining=po.total_amount - used,
        )
    return out


def stage_views(run: Run) -> list[StageView]:
    latest: dict[str, Any] = {}
    for ev in run.events:  # ordered by seq, so the last one per stage wins
        latest[ev.stage] = ev
    views: list[StageView] = []
    for stage in STAGE_ORDER:
        ev = latest.get(stage.value)
        if ev is None:
            views.append(StageView(stage=stage.value, status="PENDING", message=None, started_at=None,
                                   ended_at=None, duration_ms=None, payload={}))
            continue
        payload = dict(ev.payload_json or {})
        views.append(StageView(stage=ev.stage, status=ev.status, message=ev.message, started_at=ev.started_at,
                               ended_at=ev.ended_at, duration_ms=payload.get("duration_ms"), payload=payload))
    return views


def detail(session: Session, run: Run) -> RunDetail:
    names = vendor_names(session)
    base = summary(run, names).model_dump()
    po = po_balances(session).get(run.matched_po or "")
    return RunDetail(
        **base,
        file_hash=run.file_hash, error=run.error, reviewer_note=run.reviewer_note, reviewed_at=run.reviewed_at,
        explanation=run.explanation_json, extracted=run.extracted_json, normalized=run.normalized_json,
        stages=stage_views(run),
        rules=[RuleView(stage=r.stage, rule_id=r.rule_id, outcome=r.outcome, severity=r.severity,
                        review_reason=r.review_reason, flag=r.flag, message=r.message,
                        evidence=r.evidence_json or {}) for r in run.rules],
        po=po, file_url=f"/api/runs/{run.id}/file", events_url=f"/api/runs/{run.id}/events",
    )
