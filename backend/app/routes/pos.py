"""Purchase orders with consumed and remaining balances (A22)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_schemas import POInvoice, POView
from app.deps import get_session
from app.models import Run
from app.routes._common import po_balances
from app.schemas import Decision, RunStatus

router = APIRouter(prefix="/api/pos", tags=["purchase orders"])


@router.get("", response_model=list[POView])
def list_pos(session: Session = Depends(get_session)) -> list[POView]:
    invoices: dict[str, list[POInvoice]] = {}
    for run in session.scalars(select(Run).where(Run.matched_po.is_not(None)).order_by(Run.created_at)):
        invoices.setdefault(run.matched_po or "", []).append(POInvoice(
            run_id=run.id, filename=run.filename, invoice_number=run.invoice_number, total=run.total,
            decision=run.decision, effective_decision=run.effective_decision,
            counts_against_po=run.status == RunStatus.DONE and run.effective_decision == Decision.APPROVED,
        ))
    return [POView(**bal.model_dump(), invoices=invoices.get(po, [])) for po, bal in po_balances(session).items()]
