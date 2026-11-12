"""Creating purchase orders (A66): the number is assigned here, everything else comes from the user.

Shared by the API (`POST /api/pos`) and the CLI `demo` command, so both apply the same rules.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api_schemas import POCreate
from app.models import POLine, PurchaseOrder, Vendor
from app.money import inr, q2

_PO_NUMBER = re.compile(r"^PO-(\d{4})-(\d{4})$")


class POError(ValueError):
    """The request is understood but not allowed (unknown or blocked vendor, bad dates or totals)."""


def next_po_number(session: Session, today: date) -> str:
    """PO-<year>-<seq>: the next sequence number for the current year, starting at 0101 (A66)."""
    year = today.year
    seqs = [int(m.group(2)) for n in session.scalars(select(PurchaseOrder.po_number))
            if (m := _PO_NUMBER.match(n)) and int(m.group(1)) == year]
    return f"PO-{year}-{max(seqs, default=100) + 1:04d}"


def create_purchase_order(session: Session, body: POCreate, today: date) -> str:
    """Validate, assign the next number and save. Returns the new PO number."""
    vendor = session.get(Vendor, body.vendor_id)
    if vendor is None:
        raise POError(f"Vendor {body.vendor_id} is not in the vendor master")
    if vendor.status != "APPROVED":
        raise POError(f"{vendor.legal_name} is {vendor.status}; a PO cannot be raised for it")
    if body.issue_date > today:
        raise POError(f"Issue date {body.issue_date.isoformat()} is in the future")
    subtotal = sum((q2(l.qty * l.unit_price) for l in body.lines), Decimal("0.00"))
    total = q2(body.total_amount)
    if total < subtotal:
        raise POError(f"Total including GST ({inr(total)}) cannot be less than the line items ({inr(subtotal)})")

    for _ in range(3):  # retry if a concurrent request took the same number
        number = next_po_number(session, today)
        po = PurchaseOrder(po_number=number, vendor_id=vendor.vendor_id, issue_date=body.issue_date,
                           currency=body.currency, total_amount=total, status="OPEN")
        po.lines = [POLine(line_no=i, description=l.description, hsn_sac=l.hsn_sac, qty=l.qty, unit=l.unit,
                           unit_price=q2(l.unit_price)) for i, l in enumerate(body.lines, 1)]
        session.add(po)
        try:
            session.commit()
            return number
        except IntegrityError:
            session.rollback()
    raise POError("Could not assign a PO number, please try again")
