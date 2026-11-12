"""Hand-built extractions so unit tests depend only on the rules, never on Gemini output."""

from __future__ import annotations

from typing import Any

from app.pipeline.stages.normalize import normalize
from app.schemas import BoolField, ExtractedLine, ExtractedTax, Extraction, NormalizedInvoice, TextField


def tf(value: str | None, confidence: float = 0.98) -> TextField:
    return TextField(value=value, confidence=confidence, source_text=value)


def line(desc: str, qty: str, price: str, amount: str) -> ExtractedLine:
    return ExtractedLine(description=desc, qty=qty, unit_price=price, amount=amount, confidence=0.97)


def tax(kind: str, rate: str, amount: str) -> ExtractedTax:
    return ExtractedTax(type=kind, rate=rate, amount=amount, confidence=0.97)


HP1_LINES = [
    line("Safety helmet ISI marked (IS 2925)", "200", "350.00", "70000.00"),
    line("Industrial safety gloves (pair)", "500", "120.00", "60000.00"),
    line("Reflective safety vest", "100", "200.00", "20000.00"),
]


def make_extraction(**overrides: Any) -> Extraction:
    """HP-1 by default. Override any top-level field with a value (str/None) or a full TextField."""
    base: dict[str, Any] = {
        "vendor_name": "Shakti Industrial Supplies Pvt Ltd",
        "vendor_gstin": "27AAKCS4821M1Z5",
        "invoice_number": "INV-2026-142",
        "invoice_date": "2026-10-23",
        "due_date": "2026-11-22",
        "po_reference": "PO-2026-0101",
        "currency": "INR",
        "subtotal": "150000.00",
        "total": "177000.00",
        "bank_account": "50200012345678",
        "ifsc": "HDFC0001234",
    }
    lines = overrides.pop("line_items", HP1_LINES)
    taxes = overrides.pop("taxes", [tax("CGST", "9", "13500.00"), tax("SGST", "9", "13500.00")])
    inclusive = overrides.pop("tax_inclusive", False)
    base.update(overrides)
    fields = {k: v if isinstance(v, TextField) else tf(v) for k, v in base.items()}
    return Extraction(line_items=lines, taxes=taxes,
                      tax_inclusive=BoolField(value=inclusive, confidence=0.95, source_text=None), **fields)


def make_inv(**overrides: Any) -> NormalizedInvoice:
    _, inv = normalize(make_extraction(**overrides))
    return inv


# Scenario extractions mirroring data/invoices (see scripts/generate_invoices.py)

def ec1(number: str, desc: str, unit: str, igst: str, total: str, date: str) -> Extraction:
    return make_extraction(
        vendor_name="Vardhan Steel Fabricators Pvt Ltd", vendor_gstin="24AAECV5163P1Z2", invoice_number=number,
        invoice_date=date, due_date=None, po_reference="PO-2026-0103", subtotal=unit, total=total,
        bank_account="34567812901", ifsc="SBIN0004512",
        line_items=[line(desc, "1", unit, unit)], taxes=[tax("IGST", "18", igst)],
    )


EC1_A = ec1("VSF/2627/0311", "Fabrication and erection of MS shed structure, Milestone 1", "101694.92",
            "18305.09", "120000.00", "2026-10-03")
EC1_B = ec1("VSF/2627/0347", "Fabrication and erection of MS shed structure, Milestone 2", "101694.92",
            "18305.09", "120000.00", "2026-10-18")
EC1_C = ec1("VSF/2627/0389", "Fabrication and erection of MS shed structure, Milestone 3 (final)", "76271.19",
            "13728.81", "90000.00", "2026-11-07")
EC2 = make_extraction(invoice_number="INV/2026/0142")
EC3 = make_extraction(
    vendor_name=tf("Kaveri Office Essentials", 0.82), vendor_gstin=tf("29BQKPK2847R1ZX", 0.75),
    invoice_number=tf(None, 0.9), invoice_date=tf("2026-11-04", 0.66), due_date="2026-12-04", po_reference=None,
    subtotal="90000.00", total=tf("106200.00", 0.8), bank_account="0412101034567", ifsc="CNRB0000412",
    line_items=[line("A4 copier paper 75 GSM (ream of 500)", "300", "240.00", "72000.00"),
                line("Whiteboard markers (box of 10)", "50", "180.00", "9000.00"),
                line("Box file with spring clip", "200", "45.00", "9000.00")],
    taxes=[tax("IGST", "18", "16200.00")],
)
EC4 = make_extraction(
    vendor_name="Brightline IT Services Pvt Ltd", vendor_gstin="36AAHCB9054L1Z8", invoice_number="BITS/INV/2026/1187",
    invoice_date="2026-11-02", due_date="2026-12-02", po_reference="PO-2026-0106", subtotal="100000.00",
    total="118000.00", bank_account="045661900002345", ifsc="YESB0000456",
    line_items=[line("Laptop annual maintenance contract (per device)", "25", "3000.00", "75000.00"),
                line("On-site support visit", "10", "2500.00", "25000.00")],
    taxes=[tax("IGST", "18", "18000.00")],
)
HP2 = make_extraction(
    vendor_name="Nilgiri Packaging Solutions LLP", vendor_gstin="33AAQFN7392H1ZK", invoice_number="NPS/26-27/0871",
    invoice_date="2026-10-31", due_date="2026-11-30", po_reference="PO-2026-0102", subtotal="172550.85",
    total="203610.00", bank_account="917020045612398", ifsc="UTIB0002871", tax_inclusive=True,
    line_items=[line("Corrugated box 5-ply 18x12x12 in", "4000", "35.94", "143760.00"),
                line("Stretch wrap film roll 23 micron", "200", "299.25", "59850.00")],
    taxes=[tax("IGST", "18", "31059.15")],
)
HP3 = make_extraction(
    vendor_name="Nilgiri Packaging Solutions LLP", vendor_gstin="33AAQFN7392H1ZK", invoice_number="NPS/26-27/0904",
    invoice_date="2026-11-09", due_date="2026-12-09", po_reference="PO-2026-0108", subtotal="97000.00",
    total="114460.00", bank_account="917020045612398", ifsc="UTIB0002871",
    line_items=[line("Bubble wrap roll 1 m x 100 m", "50", "1200.00", "60000.00"),
                line("BOPP packing tape 48 mm (box of 72)", "20", "1850.00", "37000.00")],
    taxes=[tax("IGST", "18", "17460.00")],
)
