"""Load vendor master and POs from data/seed/*.csv into the DB."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import POLine, PurchaseOrder, RuleResultRow, Run, StageEvent, Vendor


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seed_master_data(session: Session, seed_dir: Path) -> dict[str, int]:
    """Replace vendors, POs and PO lines with the CSV contents. Runs are untouched."""
    session.execute(delete(POLine))
    session.execute(delete(PurchaseOrder))
    session.execute(delete(Vendor))
    vendors = _rows(seed_dir / "vendors.csv")
    for r in vendors:
        session.add(Vendor(
            vendor_id=r["vendor_id"], legal_name=r["legal_name"],
            aliases=[a.strip() for a in r["aliases"].split("|") if a.strip()],
            gstin=r["gstin"], status=r["status"], bank_account=r["bank_account"], ifsc=r["ifsc"],
            email=r["email"], phone=r["phone"], address=r["address"], state=r["state"],
        ))
    session.flush()
    pos = _rows(seed_dir / "purchase_orders.csv")
    for r in pos:
        session.add(PurchaseOrder(
            po_number=r["po_number"], vendor_id=r["vendor_id"], issue_date=date.fromisoformat(r["issue_date"]),
            currency=r["currency"], total_amount=Decimal(r["total_amount"]), status=r["status"],
        ))
    session.flush()
    lines = _rows(seed_dir / "purchase_order_lines.csv")
    for r in lines:
        session.add(POLine(
            po_number=r["po_number"], line_no=int(r["line_no"]), description=r["description"],
            hsn_sac=r["hsn_sac"], qty=Decimal(r["qty"]), unit=r["unit"], unit_price=Decimal(r["unit_price"]),
        ))
    session.commit()
    return {"vendors": len(vendors), "purchase_orders": len(pos), "po_lines": len(lines)}


def wipe_runs(session: Session) -> int:
    session.execute(delete(RuleResultRow))
    session.execute(delete(StageEvent))
    count = session.execute(delete(Run)).rowcount
    session.commit()
    return count
