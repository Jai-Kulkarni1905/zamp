"""Vendor master (bank accounts masked to the last 4 digits)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_schemas import VendorView
from app.deps import get_session
from app.models import Vendor
from app.money import mask_account

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


@router.get("", response_model=list[VendorView])
def list_vendors(session: Session = Depends(get_session)) -> list[VendorView]:
    return [
        VendorView(vendor_id=v.vendor_id, legal_name=v.legal_name, aliases=list(v.aliases), gstin=v.gstin,
                   status=v.status, bank_account_masked=mask_account(v.bank_account), ifsc=v.ifsc,
                   email=v.email, phone=v.phone, state=v.state)
        for v in session.scalars(select(Vendor).order_by(Vendor.vendor_id))
    ]
