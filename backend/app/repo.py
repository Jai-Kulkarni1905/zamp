"""DB queries that build the plain reference records the pure stage functions need."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import PurchaseOrder, Run, Vendor
from app.schemas import Decision, Flag, POLineRec, PORec, PriorRun, RunStatus, VendorRec


def load_vendors(session: Session) -> list[VendorRec]:
    return [
        VendorRec(
            vendor_id=v.vendor_id, legal_name=v.legal_name, aliases=list(v.aliases), gstin=v.gstin,
            status=v.status, bank_account=v.bank_account, ifsc=v.ifsc, email=v.email, phone=v.phone,
        )
        for v in session.scalars(select(Vendor).order_by(Vendor.vendor_id))
    ]


def consumed_by_po(session: Session, exclude_run_id: str | None = None) -> dict[str, Decimal]:
    """Sum of totals of runs whose effective decision is APPROVED, per PO (A22)."""
    consumed: dict[str, Decimal] = {}
    q = select(Run).where(Run.status == RunStatus.DONE, Run.matched_po.is_not(None))
    for run in session.scalars(q):
        if run.id == exclude_run_id or run.total is None or run.matched_po is None:
            continue
        if run.effective_decision == Decision.APPROVED:
            consumed[run.matched_po] = consumed.get(run.matched_po, Decimal("0.00")) + run.total
    return consumed


def load_pos(session: Session, exclude_run_id: str | None = None) -> dict[str, PORec]:
    consumed = consumed_by_po(session, exclude_run_id)
    pos = session.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)))
    return {
        po.po_number: PORec(
            po_number=po.po_number, vendor_id=po.vendor_id, status=po.status, currency=po.currency,
            total=po.total_amount, consumed=consumed.get(po.po_number, Decimal("0.00")),
            lines=[POLineRec(line_no=l.line_no, description=l.description, qty=l.qty, unit=l.unit,
                             unit_price=l.unit_price) for l in po.lines],
        )
        for po in pos
    }


def prior_runs(session: Session, exclude_run_id: str) -> list[PriorRun]:
    """Earlier finished runs for duplicate checks, minus runs rejected as duplicates (A26)."""
    out: list[PriorRun] = []
    q = select(Run).where(Run.status == RunStatus.DONE, Run.id != exclude_run_id).order_by(Run.created_at)
    for run in session.scalars(q):
        if Flag.DUPLICATE in (run.flags or []):
            continue
        out.append(PriorRun(
            run_id=run.id, filename=run.filename, file_hash=run.file_hash, vendor_key=run.vendor_key,
            invoice_number=run.invoice_number, invoice_number_canonical=run.invoice_number_canonical,
            invoice_date=run.invoice_date, total=run.total,
        ))
    return out


def hash_seen_before(session: Session, file_hash: str, exclude_run_id: str) -> bool:
    q = select(Run.id).where(Run.file_hash == file_hash, Run.id != exclude_run_id, Run.status == RunStatus.DONE)
    return session.scalars(q).first() is not None
