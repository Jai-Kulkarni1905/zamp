"""Purchase orders: balances (A22) and creating new ones with an auto-assigned number (A66)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api_schemas import NextPONumber, POCreate, POInvoice, POLineOut, POView
from app.config import Settings
from app.deps import get_app_settings, get_session
from app.models import PurchaseOrder, Run
from app.purchase_orders import POError, create_purchase_order, next_po_number
from app.routes._common import po_balances
from app.schemas import Decision, RunStatus

router = APIRouter(prefix="/api/pos", tags=["purchase orders"])

def _views(session: Session, only: str | None = None) -> list[POView]:
    invoices: dict[str, list[POInvoice]] = {}
    for run in session.scalars(select(Run).where(Run.matched_po.is_not(None)).order_by(Run.created_at)):
        invoices.setdefault(run.matched_po or "", []).append(POInvoice(
            run_id=run.id, filename=run.filename, invoice_number=run.invoice_number, total=run.total,
            decision=run.decision, effective_decision=run.effective_decision,
            counts_against_po=run.status == RunStatus.DONE and run.effective_decision == Decision.APPROVED,
        ))
    lines = {po.po_number: [POLineOut(line_no=l.line_no, description=l.description, hsn_sac=l.hsn_sac, qty=l.qty,
                                      unit=l.unit, unit_price=l.unit_price) for l in po.lines]
             for po in session.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)))}
    return [POView(**bal.model_dump(), invoices=invoices.get(po, []), lines=lines.get(po, []))
            for po, bal in po_balances(session).items() if only is None or po == only]


@router.get("", response_model=list[POView])
def list_pos(session: Session = Depends(get_session)) -> list[POView]:
    return _views(session)


@router.get("/next-number", response_model=NextPONumber)
def peek_next_number(session: Session = Depends(get_session),
                     settings: Settings = Depends(get_app_settings)) -> NextPONumber:
    """The number the next new PO will get, so the form can show it before saving."""
    return NextPONumber(po_number=next_po_number(session, settings.today()))


@router.post("", response_model=POView, status_code=201)
def create_po(body: POCreate, session: Session = Depends(get_session),
              settings: Settings = Depends(get_app_settings)) -> POView:
    try:
        number = create_purchase_order(session, body, settings.today())
    except POError as exc:
        raise HTTPException(400, str(exc)) from None
    return _views(session, only=number)[0]
