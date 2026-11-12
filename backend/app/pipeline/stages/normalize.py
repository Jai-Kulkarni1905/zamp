"""Stage 3: dates to ISO, money to Decimal, canonical numbers, GSTIN/IFSC cleanup."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.money import canonical_ref, parse_amount
from app.pipeline.stages._rules import rule
from app.schemas import (
    TOP_LEVEL_FIELDS,
    Extraction,
    NormalizedInvoice,
    NormLine,
    NormTax,
    Outcome,
    Severity,
    Stage,
    StageResult,
)

# Day-first formats come before month-first ones: Indian invoices write 07/11/2026 for 7 November.
DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y",
    "%d-%B-%Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%y", "%d-%b-%y",
]
_CURRENCY_ALIASES = {"INR", "RS", "RS.", "₹", "RUPEES", "RUPEE"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _alnum_upper(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return cleaned or None


def normalize_currency(value: str | None) -> tuple[str, bool]:
    """Returns (currency, assumed). Missing currency is assumed INR (A41)."""
    if not value:
        return "INR", True
    v = value.strip().upper()
    return ("INR" if v in _CURRENCY_ALIASES else v), False


def normalize(ex: Extraction) -> tuple[StageResult, NormalizedInvoice]:
    unparsed: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    def amount(field: str, raw: str | None) -> Decimal | None:
        value = parse_amount(raw)
        if raw and value is None:
            unparsed.append({"field": field, "raw": raw})
        return value

    def a_date(field: str, raw: str | None) -> date | None:
        value = parse_date(raw)
        if raw and value is None:
            unparsed.append({"field": field, "raw": raw})
        return value

    currency, currency_assumed = normalize_currency(ex.currency.value)
    lines = [
        NormLine(
            description=(li.description or "").strip(),
            qty=amount("line_items.qty", li.qty),
            unit_price=amount("line_items.unit_price", li.unit_price),
            amount=amount("line_items.amount", li.amount),
        )
        for li in ex.line_items
    ]
    taxes = [
        NormTax(type=(t.type or "TAX").strip().upper(), rate=parse_amount(t.rate), amount=amount("taxes.amount", t.amount))
        for t in ex.taxes
    ]
    inv = NormalizedInvoice(
        vendor_name=_clean(ex.vendor_name.value),
        vendor_gstin=_alnum_upper(ex.vendor_gstin.value),
        invoice_number=_clean(ex.invoice_number.value),
        invoice_number_canonical=canonical_ref(ex.invoice_number.value),
        invoice_date=a_date("invoice_date", ex.invoice_date.value),
        due_date=a_date("due_date", ex.due_date.value),
        po_reference=_clean(ex.po_reference.value),
        po_reference_canonical=canonical_ref(ex.po_reference.value),
        currency=currency,
        line_items=lines,
        subtotal=amount("subtotal", ex.subtotal.value),
        taxes=taxes,
        tax_inclusive=bool(ex.tax_inclusive.value),
        total=amount("total", ex.total.value),
        bank_account=_alnum_upper(ex.bank_account.value),
        ifsc=_alnum_upper(ex.ifsc.value),
        confidence={name: getattr(ex, name).confidence for name in TOP_LEVEL_FIELDS},
    )

    for field in ("invoice_number", "po_reference", "invoice_date", "due_date", "subtotal", "total", "vendor_gstin",
                  "bank_account", "ifsc", "currency"):
        raw = getattr(ex, field).value
        canon_field = f"{field}_canonical" if field in ("invoice_number", "po_reference") else field
        new = getattr(inv, canon_field)
        shown = new.isoformat() if isinstance(new, date) else (str(new) if new is not None else None)
        if raw != shown and not (raw is None and field == "currency"):
            changes.append({"field": field, "raw": raw, "normalized": shown})
    if currency_assumed:
        changes.append({"field": "currency", "raw": None, "normalized": "INR (assumed, not printed)"})

    parse_rule = rule(
        Stage.NORMALIZE, "NORM-PARSE",
        Outcome.WARN if unparsed else Outcome.PASS, Severity.INFO,
        f"Could not parse {', '.join(u['field'] for u in unparsed)}; treated as missing" if unparsed
        else "All values parsed",
        {"unparsed": unparsed},
    )
    message = f"{len(changes)} fields normalized" + (f", {len(unparsed)} unparseable" if unparsed else "")
    payload = {"changes": changes, "normalized": inv.model_dump(mode="json")}
    return StageResult(stage=Stage.NORMALIZE, message=message, payload=payload, rules=[parse_rule]), inv
