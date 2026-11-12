"""Generate the test invoice PDFs for every scenario in PLAN.md section 7.

Reads vendors and PO lines from data/seed/, renders each scenario with one of three
visually distinct templates, and writes data/invoices/<ID>.pdf plus manifest.json.

Output is byte-for-byte deterministic for a given --as-of date (reportlab invariant mode,
seeded scan noise), so file hashes, and therefore cached Gemini fixtures, stay stable.

Usage:
    python scripts/generate_invoices.py [--as-of 2026-11-12] [--out data/invoices]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image, ImageFilter
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

rl_config.invariant = 1

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
DEFAULT_AS_OF = date(2026, 11, 12)
GST_RATE = Decimal("18")
TWO = Decimal("0.01")

BUYER = {
    "name": "Meridian Retail Pvt Ltd",
    "address": "Unit 7B, Tower 2, Commerzone, Yerwada, Pune 411006",
    "state": "Maharashtra",
    "state_code": "27",
    "gstin": "27AAFCM6610K1Z3",
}


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


def inr(value: Decimal) -> str:
    """Format with Indian digit grouping: 1,77,000.00"""
    value = q2(value)
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}{whole}.{frac}"


_ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
    "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _words_below_1000(n: int) -> str:
    parts: list[str] = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_in_words(value: Decimal) -> str:
    """Indian system: Rupees One Lakh Seventy Seven Thousand Only."""
    value = q2(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)
    parts: list[str] = []
    for unit, size in (("Crore", 10_000_000), ("Lakh", 100_000), ("Thousand", 1000)):
        if rupees >= size:
            parts.append(f"{_words_below_1000(rupees // size)} {unit}")
            rupees %= size
    if rupees:
        parts.append(_words_below_1000(rupees))
    text = "Rupees " + (" ".join(parts) if parts else "Zero")
    if paise:
        text += f" and {_words_below_1000(paise)} Paise"
    return text + " Only"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Line:
    description: str
    hsn: str
    qty: Decimal
    unit: str
    rate: Decimal

    @property
    def amount(self) -> Decimal:
        return q2(self.qty * self.rate)


@dataclass
class Invoice:
    scenario_id: str
    template: str
    vendor: dict[str, str]
    number: str | None
    invoice_date: date
    due_date: date
    po_ref: str | None
    lines: list[Line]
    tax_inclusive: bool = False
    bank_account: str = ""
    ifsc: str = ""
    bank_name: str = ""
    note: str | None = None
    expected: dict[str, object] = field(default_factory=dict)

    @property
    def intra_state(self) -> bool:
        return self.vendor["state"] == BUYER["state"]

    @property
    def line_total(self) -> Decimal:
        return sum((l.amount for l in self.lines), Decimal("0"))

    def computed(self) -> dict[str, object]:
        """Taxable value, tax rows, round off and grand total."""
        rate = GST_RATE / 100
        if self.tax_inclusive:
            total = self.line_total
            taxable = q2(total / (1 + rate))
            tax_total = total - taxable
            round_off = Decimal("0.00")
        else:
            taxable = self.line_total
            tax_total = q2(taxable * rate) if not self.intra_state else 2 * q2(taxable * rate / 2)
            raw = taxable + tax_total
            total = raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            round_off = total - raw
        if self.intra_state:
            cgst = q2(tax_total / 2)
            taxes = [("CGST", GST_RATE / 2, cgst), ("SGST", GST_RATE / 2, tax_total - cgst)]
        else:
            taxes = [("IGST", GST_RATE, tax_total)]
        return {"taxable": taxable, "taxes": taxes, "round_off": round_off, "total": q2(total)}


def load_seed() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, list[Line]]]:
    with open(SEED / "vendors.csv", newline="", encoding="utf-8") as f:
        vendors = {r["vendor_id"]: r for r in csv.DictReader(f)}
    with open(SEED / "purchase_orders.csv", newline="", encoding="utf-8") as f:
        pos = {r["po_number"]: r for r in csv.DictReader(f)}
    lines: dict[str, list[Line]] = {}
    with open(SEED / "purchase_order_lines.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            lines.setdefault(r["po_number"], []).append(
                Line(r["description"], r["hsn_sac"], Decimal(r["qty"]), r["unit"], Decimal(r["unit_price"]))
            )
    return vendors, pos, lines


BANK_NAMES = {
    "HDFC": "HDFC Bank",
    "UTIB": "Axis Bank",
    "SBIN": "State Bank of India",
    "CNRB": "Canara Bank",
    "ICIC": "ICICI Bank",
    "KKBK": "Kotak Mahindra Bank",
    "YESB": "Yes Bank",
}


def build_scenarios(as_of: date) -> list[Invoice]:
    vendors, _pos, po_lines = load_seed()

    def inv(
        scenario_id: str,
        template: str,
        vendor_id: str,
        number: str | None,
        days_ago: int,
        po_ref: str | None,
        lines: list[Line],
        expected: dict[str, object],
        **kwargs: object,
    ) -> Invoice:
        v = vendors[vendor_id]
        invoice_date = as_of - timedelta(days=days_ago)
        bank_account = str(kwargs.pop("bank_account", v["bank_account"]))
        ifsc = str(kwargs.pop("ifsc", v["ifsc"]))
        return Invoice(
            scenario_id=scenario_id,
            template=template,
            vendor=v,
            number=number,
            invoice_date=invoice_date,
            due_date=invoice_date + timedelta(days=30),
            po_ref=po_ref,
            lines=lines,
            bank_account=bank_account,
            ifsc=ifsc,
            bank_name=BANK_NAMES[ifsc[:4]],
            expected=expected,
            **kwargs,  # type: ignore[arg-type]
        )

    hp1_lines = po_lines["PO-2026-0101"]
    m1, m2, m3 = po_lines["PO-2026-0103"]
    hp2_lines = [
        Line(po_lines["PO-2026-0102"][0].description, "4819", Decimal("4000"), "Nos", Decimal("35.94")),
        Line(po_lines["PO-2026-0102"][1].description, "3920", Decimal("200"), "Rolls", Decimal("299.25")),
    ]
    ec1c_line = Line(m3.description + " (final)", m3.hsn, Decimal("1"), "Lot", Decimal("76271.19"))

    return [
        inv("HP-1", "classic", "V001", "INV-2026-142", 20, "PO-2026-0101", hp1_lines,
            {"decision": "APPROVED", "flags": []}),
        inv("HP-2", "modern", "V002", "NPS/26-27/0871", 12, "PO-2026-0102", hp2_lines,
            {"decision": "APPROVED", "flags": [], "note": "1.5% over PO, within tolerance"},
            tax_inclusive=True),
        inv("EC-1-A", "compact", "V003", "VSF/2627/0311", 40, "PO-2026-0103", [m1],
            {"decision": "APPROVED", "flags": []}),
        inv("EC-1-B", "compact", "V003", "VSF/2627/0347", 25, "PO-2026-0103", [m2],
            {"decision": "APPROVED", "flags": []}),
        inv("EC-1-C", "compact", "V003", "VSF/2627/0389", 5, "PO-2026-0103", [ec1c_line],
            {"decision": "NEEDS_REVIEW", "flags": ["OVER_PO"],
             "note": "exceeds remaining Rs 60,000 by Rs 30,000"}),
        inv("EC-2", "modern", "V001", "INV/2026/0142", 20, "PO-2026-0101", hp1_lines,
            {"decision": "REJECTED", "flags": ["DUPLICATE"], "duplicate_of": "HP-1"}),
        inv("EC-3", "scanned", "V004", None, 8, None, po_lines["PO-2026-0104"],
            {"decision": "NEEDS_REVIEW", "flags": ["LOW_CONFIDENCE", "PO_INFERRED"],
             "inferred_po": "PO-2026-0104", "missing": ["invoice_number", "po_reference"]}),
        inv("EC-4", "modern", "V005", "BITS/INV/2026/1187", 10, "PO-2026-0106", po_lines["PO-2026-0106"],
            {"decision": "NEEDS_REVIEW", "flags": ["FRAUD_RISK"]},
            bank_account="045661900002345", ifsc="YESB0000456",
            note="Please note: we have changed our bank. Kindly remit all payments to the new "
                 "account shown in the payment details above, with immediate effect."),
        # HP-3 bills a PO that is NOT in the seed data: it is created in the app first (A66, A67).
        inv("HP-3", "modern", "V002", "NPS/26-27/0904", 3, HP3_PO["po_number"], HP3_LINES,
            {"decision": "APPROVED", "flags": [], "requires_po": HP3_PO}),
    ]


# The PO that HP-3 bills. It is typed into the "New purchase order" form (or created by the demo tools)
# before HP-3 is uploaded; with the 7 seeded POs the auto-assigned number is PO-2026-0108.
HP3_LINES = [
    Line("Bubble wrap roll 1 m x 100 m", "3923", Decimal("50"), "Rolls", Decimal("1200.00")),
    Line("BOPP packing tape 48 mm (box of 72)", "3919", Decimal("20"), "Boxes", Decimal("1850.00")),
]
HP3_PO: dict[str, object] = {
    "po_number": "PO-2026-0108",
    "vendor_id": "V002",
    "issue_date_days_ago": 5,
    "total_amount": "114460.00",  # 97,000.00 lines + 18% IGST 17,460.00
    "lines": [{"description": l.description, "hsn_sac": l.hsn, "qty": str(l.qty), "unit": l.unit,
               "unit_price": str(l.rate)} for l in HP3_LINES],
}


# ---------------------------------------------------------------------------
# Shared rendering helpers
# ---------------------------------------------------------------------------


def style(name: str, font: str = "Helvetica", size: float = 9, **kw: object) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=size * 1.3, **kw)  # type: ignore[arg-type]


def qty_str(q: Decimal) -> str:
    return f"{q:,.0f}" if q == q.to_integral_value() else f"{q:,.2f}"


def fmt_date(d: date, pattern: str) -> str:
    return d.strftime(pattern)


def new_doc(buf: io.BytesIO, inv: Invoice, top: float = 14 * mm) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=top,
        bottomMargin=16 * mm,
        title=f"Invoice {inv.number or ''}".strip(),
        author=inv.vendor["legal_name"],
        creator="",
        producer="",
        invariant=1,
    )


# ---------------------------------------------------------------------------
# Template 1: classic bordered GST tax invoice
# ---------------------------------------------------------------------------


def render_classic(inv: Invoice) -> bytes:
    buf = io.BytesIO()
    doc = new_doc(buf, inv)
    v = inv.vendor
    c = inv.computed()
    body = style("cb")
    small = style("cs", size=8)
    bold = style("cbo", "Helvetica-Bold")
    W = doc.width

    title = Table(
        [[Paragraph("<b>TAX INVOICE</b>", style("t", "Helvetica-Bold", 15, alignment=TA_CENTER))],
         [Paragraph("Original for Recipient", style("t2", size=7.5, alignment=TA_RIGHT))]],
        colWidths=[W],
    )
    title.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))

    seller = [
        Paragraph(f"<b>{v['legal_name']}</b>", style("sn", "Helvetica-Bold", 12)),
        Paragraph(v["address"], body),
        Paragraph(f"State: {v['state']}", body),
        Paragraph(f"GSTIN/UIN: <b>{v['gstin']}</b>", body),
        Paragraph(f"Email: {v['email']} | Ph: {v['phone']}", small),
    ]
    meta_rows = [
        ["Invoice No.", inv.number or ""],
        ["Invoice Date", fmt_date(inv.invoice_date, "%d-%b-%Y")],
        ["Due Date", fmt_date(inv.due_date, "%d-%b-%Y")],
    ]
    if inv.po_ref:
        meta_rows.append(["Buyer's Order No.", inv.po_ref])
    meta_rows.append(["Place of Supply", f"{BUYER['state']} ({BUYER['state_code']})"])
    meta = Table([[Paragraph(a, small), Paragraph(f"<b>{b}</b>", body)] for a, b in meta_rows],
                 colWidths=[30 * mm, None])
    meta.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (0, -1), [colors.whitesmoke]),
    ]))
    buyer = [
        Paragraph("Buyer (Bill to)", small),
        Paragraph(f"<b>{BUYER['name']}</b>", bold),
        Paragraph(BUYER["address"], body),
        Paragraph(f"GSTIN/UIN: {BUYER['gstin']}", body),
        Paragraph(f"State: {BUYER['state']}, Code: {BUYER['state_code']}", body),
    ]
    header = Table([[seller, meta], [buyer, ""]], colWidths=[W * 0.55, W * 0.45])
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("SPAN", (1, 0), (1, 1)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (1, 0), (1, 0), 0),
    ]))

    rows: list[list[object]] = [["S.No", "Description of Goods / Services", "HSN/SAC", "Qty", "Unit", "Rate", "Amount"]]
    for i, l in enumerate(inv.lines, 1):
        rows.append([str(i), Paragraph(l.description, body), l.hsn, qty_str(l.qty), l.unit, inr(l.rate), inr(l.amount)])
    filler = max(0, 8 - len(inv.lines))
    rows += [[""] * 7 for _ in range(filler)]
    items = Table(rows, colWidths=[11 * mm, None, 18 * mm, 16 * mm, 14 * mm, 24 * mm, 28 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.4, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    tot_rows = [["Taxable Value", inr(c["taxable"])]]
    for name, rate, amt in c["taxes"]:  # type: ignore[union-attr]
        tot_rows.append([f"{name} @ {rate.normalize()}%", inr(amt)])
    if c["round_off"]:
        tot_rows.append(["Round Off", inr(c["round_off"])])  # type: ignore[arg-type]
    tot_rows.append(["Grand Total (Rs.)", inr(c["total"])])  # type: ignore[arg-type]
    totals = Table(tot_rows, colWidths=[38 * mm, 30 * mm])
    totals.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
    ]))
    words = [
        Paragraph("Amount Chargeable (in words)", small),
        Paragraph(f"<b>{amount_in_words(c['total'])}</b>", body),  # type: ignore[arg-type]
        Spacer(1, 6),
        Paragraph("Company's Bank Details", small),
        Paragraph(f"Bank Name: <b>{inv.bank_name}</b>", body),
        Paragraph(f"A/c No.: <b>{inv.bank_account}</b>", body),
        Paragraph(f"IFSC: <b>{inv.ifsc}</b>", body),
    ]
    summary = Table([[words, totals]], colWidths=[W - 70 * mm, 70 * mm])
    summary.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (1, 0), (1, 0), 0),
    ]))

    city = v["address"].split(",")[-1].strip().split(" ")[0]
    sign = Table(
        [[Paragraph("Declaration: We declare that this invoice shows the actual price of the goods "
                    "described and that all particulars are true and correct.", small),
          Paragraph(f"for <b>{v['legal_name']}</b><br/><br/><br/>Authorised Signatory",
                    style("sg", size=9, alignment=TA_RIGHT))]],
        colWidths=[W * 0.55, W * 0.45],
    )
    sign.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [title, header, items, summary, sign, Spacer(1, 4),
             Paragraph(f"SUBJECT TO {city.upper()} JURISDICTION. This is a computer generated invoice.",
                       style("ft", size=7.5, alignment=TA_CENTER))]
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Template 2: modern header band, borderless striped table
# ---------------------------------------------------------------------------

ACCENTS = {"V001": "#1F3A5F", "V002": "#0F766E", "V005": "#5B3FA6"}


def render_modern(inv: Invoice) -> bytes:
    buf = io.BytesIO()
    doc = new_doc(buf, inv, top=46 * mm)
    v = inv.vendor
    c = inv.computed()
    accent = colors.HexColor(ACCENTS.get(v["vendor_id"], "#334155"))
    W = doc.width
    label = style("ml", size=7.5, textColor=colors.HexColor("#6B7280"))
    body = style("mb", size=9)
    bold = style("mbo", "Helvetica-Bold", 9.5)

    def page(canvas: Canvas, _doc: object) -> None:
        pw, ph = A4
        canvas.saveState()
        canvas.setFillColor(accent)
        canvas.rect(0, ph - 34 * mm, pw, 34 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawString(14 * mm, ph - 16 * mm, v["legal_name"])
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(14 * mm, ph - 22 * mm, v["address"])
        canvas.drawString(14 * mm, ph - 27 * mm, f"GSTIN {v['gstin']}   |   {v['email']}   |   {v['phone']}")
        canvas.setFont("Helvetica-Bold", 24)
        canvas.drawRightString(pw - 14 * mm, ph - 17 * mm, "INVOICE")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(pw - 14 * mm, ph - 23 * mm,
                               "Tax Invoice (prices inclusive of GST)" if inv.tax_inclusive else "Tax Invoice")
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(1)
        canvas.line(14 * mm, 12 * mm, pw - 14 * mm, 12 * mm)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(14 * mm, 8 * mm, f"Thank you for your business. Queries: {v['email']}")
        canvas.drawRightString(pw - 14 * mm, 8 * mm, "Page 1 of 1")
        canvas.restoreState()

    details = Table(
        [[
            [Paragraph("BILLED TO", label), Paragraph(BUYER["name"], bold), Paragraph(BUYER["address"], body),
             Paragraph(f"GSTIN {BUYER['gstin']}", body)],
            [Paragraph("INVOICE NUMBER", label), Paragraph(inv.number or "", bold), Spacer(1, 3),
             Paragraph("PURCHASE ORDER", label), Paragraph(inv.po_ref or "", bold)],
            [Paragraph("ISSUED", label), Paragraph(fmt_date(inv.invoice_date, "%d %B %Y"), bold), Spacer(1, 3),
             Paragraph("PAYMENT DUE", label), Paragraph(fmt_date(inv.due_date, "%d %B %Y"), bold)],
        ]],
        colWidths=[W * 0.44, W * 0.30, W * 0.26],
    )
    details.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))

    rate_hdr = "Rate (incl. GST)" if inv.tax_inclusive else "Rate"
    rows: list[list[object]] = [["#", "Item", "HSN", "Qty", rate_hdr, "Amount (Rs.)"]]
    for i, l in enumerate(inv.lines, 1):
        rows.append([str(i), Paragraph(l.description, body), l.hsn, f"{qty_str(l.qty)} {l.unit}", inr(l.rate), inr(l.amount)])
    items = Table(rows, colWidths=[8 * mm, None, 16 * mm, 24 * mm, 28 * mm, 30 * mm])
    items.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.HexColor("#D1D5DB")),
    ]))

    if inv.tax_inclusive:
        tot_rows = [["Total (incl. GST)", inr(c["total"])], ["Taxable value", inr(c["taxable"])]]  # type: ignore[arg-type]
        for name, rate, amt in c["taxes"]:  # type: ignore[union-attr]
            tot_rows.append([f"{name} {rate.normalize()}% (included)", inr(amt)])
        tot_rows.append(["Amount payable", f"Rs. {inr(c['total'])}"])  # type: ignore[arg-type]
    else:
        tot_rows = [["Subtotal", inr(c["taxable"])]]  # type: ignore[arg-type]
        for name, rate, amt in c["taxes"]:  # type: ignore[union-attr]
            tot_rows.append([f"{name} {rate.normalize()}%", inr(amt)])
        if c["round_off"]:
            tot_rows.append(["Round off", inr(c["round_off"])])  # type: ignore[arg-type]
        tot_rows.append(["Amount payable", f"Rs. {inr(c['total'])}"])  # type: ignore[arg-type]
    totals = Table(tot_rows, colWidths=[46 * mm, 34 * mm])
    totals.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), accent),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]))

    pay = [
        Paragraph("PAYMENT DETAILS", label),
        Paragraph(f"Account name: {v['legal_name']}", body),
        Paragraph(f"Bank: {inv.bank_name}", body),
        Paragraph(f"Account no: <b>{inv.bank_account}</b>", body),
        Paragraph(f"IFSC: <b>{inv.ifsc}</b>", body),
        Spacer(1, 6),
        Paragraph(amount_in_words(c["total"]), style("aw", "Helvetica-Oblique", 8.5)),  # type: ignore[arg-type]
    ]
    bottom = Table([[pay, totals]], colWidths=[W - 82 * mm, 82 * mm])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))

    story: list[object] = [details, Spacer(1, 8), items, Spacer(1, 10), bottom]
    if inv.note:
        note = Table([[Paragraph(f"<b>{inv.note}</b>", style("nt", size=9, textColor=colors.HexColor("#92400E")))]],
                     colWidths=[W])
        note.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#F59E0B")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story += [Spacer(1, 10), note]
    story += [Spacer(1, 22), KeepTogether([
        Paragraph(f"For {v['legal_name']}", style("fs", size=9, alignment=TA_RIGHT)),
        Spacer(1, 16),
        Paragraph("Authorised signatory", style("fs2", size=8, alignment=TA_RIGHT, textColor=colors.HexColor("#6B7280"))),
    ])]
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Template 3: compact monospace ERP printout
# ---------------------------------------------------------------------------


def render_compact(inv: Invoice) -> bytes:
    buf = io.BytesIO()
    doc = new_doc(buf, inv, top=12 * mm)
    v = inv.vendor
    c = inv.computed()
    W = doc.width
    mono = style("cm", "Courier", 8.5)
    monob = style("cmb", "Courier-Bold", 8.5)
    dash = (1.5, 1.5)

    def rule(width: float = 0.6, dashed: bool = False) -> Table:
        t = Table([[""]], colWidths=[W], rowHeights=[2])
        t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), width, colors.black, None, dash if dashed else None)]))
        return t

    head = [
        Paragraph(v["legal_name"].upper(), style("ch", "Courier-Bold", 13, alignment=TA_CENTER)),
        Paragraph(v["address"], style("ca", "Courier", 8.5, alignment=TA_CENTER)),
        Paragraph(f"GSTIN: {v['gstin']}  PH: {v['phone']}  {v['email']}", style("cg", "Courier", 8, alignment=TA_CENTER)),
        Spacer(1, 4), rule(1.2),
        Paragraph("GST INVOICE", style("ct", "Courier-Bold", 11, alignment=TA_CENTER)),
        rule(1.2), Spacer(1, 4),
    ]

    def kv(rows: list[tuple[str, str]]) -> Table:
        t = Table([[Paragraph(k, mono), Paragraph(": " + val, monob)] for k, val in rows], colWidths=[30 * mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return t

    left = kv([("BILL TO", BUYER["name"]), ("ADDRESS", BUYER["address"]), ("GSTIN", BUYER["gstin"]),
               ("PLACE OF SUPPLY", f"{BUYER['state_code']}-{BUYER['state'].upper()}")])
    right = kv([("INVOICE NO", inv.number or ""), ("INVOICE DT", fmt_date(inv.invoice_date, "%d/%m/%Y")),
                ("PO NO", inv.po_ref or ""), ("DUE DT", fmt_date(inv.due_date, "%d/%m/%Y")),
                ("TERMS", "NET 30")])
    info = Table([[left, right]], colWidths=[W * 0.58, W * 0.42])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    rows: list[list[object]] = [["SL", "PARTICULARS", "SAC/HSN", "QTY", "UOM", "RATE", "VALUE (INR)"]]
    for i, l in enumerate(inv.lines, 1):
        rows.append([f"{i:02d}", Paragraph(l.description.upper(), mono), l.hsn, qty_str(l.qty), l.unit.upper(),
                     inr(l.rate), inr(l.amount)])
    items = Table(rows, colWidths=[9 * mm, None, 18 * mm, 12 * mm, 12 * mm, 26 * mm, 28 * mm])
    items.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Courier-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Courier", 8.5),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black, None, dash),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black, None, dash),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.black, None, dash),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))

    tot_rows = [["TAXABLE VALUE", inr(c["taxable"])]]  # type: ignore[arg-type]
    for name, rate, amt in c["taxes"]:  # type: ignore[union-attr]
        tot_rows.append([f"ADD: {name} @{rate.normalize()}%", inr(amt)])
    if c["round_off"]:
        tot_rows.append(["ROUND OFF", inr(c["round_off"])])  # type: ignore[arg-type]
    tot_rows.append(["NET PAYABLE INR", inr(c["total"])])  # type: ignore[arg-type]
    totals = Table(tot_rows, colWidths=[W - 34 * mm, 34 * mm])
    totals.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Courier", 8.5),
        ("FONT", (0, -1), (-1, -1), "Courier-Bold", 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black, None, dash),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, colors.black),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
    ]))

    bank = kv([("BANK", inv.bank_name.upper()), ("A/C NO", inv.bank_account), ("IFSC", inv.ifsc)])
    story = head + [info, Spacer(1, 6), items, Spacer(1, 2), totals, Spacer(1, 4),
                    Paragraph("INR " + amount_in_words(c["total"]).upper(), monob),  # type: ignore[arg-type]
                    Spacer(1, 8), rule(dashed=True), Paragraph("REMITTANCE", monob), bank, rule(dashed=True),
                    Spacer(1, 6),
                    Paragraph("E. &amp; O.E. | INTEREST @18% P.A. CHARGED ON OVERDUE BILLS | "
                              "SYSTEM GENERATED DOCUMENT", style("cf", "Courier", 7)),
                    Spacer(1, 18),
                    Paragraph(f"FOR {v['legal_name'].upper()}", style("cs1", "Courier-Bold", 8.5, alignment=TA_RIGHT)),
                    Spacer(1, 18),
                    Paragraph("AUTHORISED SIGNATORY", style("cs2", "Courier", 8, alignment=TA_RIGHT))]
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# "Scanned" variant: classic layout rasterised, rotated, noisy, image-only PDF
# ---------------------------------------------------------------------------


def render_scanned(inv: Invoice) -> bytes:
    source = render_classic(inv)
    with pymupdf.open(stream=source, filetype="pdf") as pdf:
        pix = pdf[0].get_pixmap(dpi=130, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)

    rnd = random.Random(1142)
    img = img.point(lambda p: int(p * 0.86 + 22))  # greyer paper, softer black
    noise = Image.frombytes("L", img.size, rnd.randbytes(img.width * img.height))
    img = Image.blend(img, noise, 0.09)
    img = img.rotate(1.6, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=196)
    img = img.filter(ImageFilter.GaussianBlur(0.7))

    jpg = io.BytesIO()
    img.save(jpg, "JPEG", quality=62)
    jpg.seek(0)

    out = io.BytesIO()
    canvas = Canvas(out, pagesize=A4, invariant=1)
    canvas.setTitle("scan0008")
    canvas.drawImage(ImageReader(jpg), 0, 0, width=A4[0], height=A4[1])
    canvas.showPage()
    canvas.save()
    return out.getvalue()


RENDERERS: dict[str, Callable[[Invoice], bytes]] = {
    "classic": render_classic,
    "modern": render_modern,
    "compact": render_compact,
    "scanned": render_scanned,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF,
                        help="anchor date that invoice dates are relative to (default %(default)s)")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "invoices")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for order, inv in enumerate(build_scenarios(args.as_of), 1):
        pdf = RENDERERS[inv.template](inv)
        path = args.out / f"{inv.scenario_id}.pdf"
        path.write_bytes(pdf)
        c = inv.computed()
        manifest.append({
            "run_order": order,
            "id": inv.scenario_id,
            "file": path.name,
            "sha256": hashlib.sha256(pdf).hexdigest(),
            "template": inv.template,
            "vendor_id": inv.vendor["vendor_id"],
            "invoice_number": inv.number,
            "invoice_date": inv.invoice_date.isoformat(),
            "po_reference": inv.po_ref,
            "tax_inclusive": inv.tax_inclusive,
            "taxable": str(c["taxable"]),
            "total": str(c["total"]),
            "bank_account": inv.bank_account,
            "ifsc": inv.ifsc,
            "expected": inv.expected,
        })
        print(f"{order}. {path.name:<11} {inv.template:<8} {inv.vendor['vendor_id']}  "
              f"Rs. {inr(c['total']):>12}  -> {inv.expected['decision']}")  # type: ignore[arg-type]

    (args.out / "manifest.json").write_text(
        json.dumps({"as_of": args.as_of.isoformat(), "invoices": manifest}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(manifest)} PDFs and manifest.json to {args.out}")


if __name__ == "__main__":
    main()
