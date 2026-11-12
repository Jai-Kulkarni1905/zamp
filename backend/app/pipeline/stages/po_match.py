"""Stage 6 (PO match, A20 and A21) and stage 7 (amount check, A22 to A24, A36)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from rapidfuzz import fuzz

from app.config import T
from app.money import canonical_ref, inr, q2
from app.pipeline.stages._rules import rule, skipped
from app.pipeline.stages.vendor import VendorMatch
from app.schemas import Flag, NormalizedInvoice, Outcome, POLineRec, PORec, RuleResult, Severity, Stage, StageResult

S_PO = Stage.PO_MATCH
S_AMT = Stage.AMOUNT


@dataclass
class POMatch:
    po: PORec
    match_type: Literal["EXPLICIT", "INFERRED"]


def tolerance(remaining: Decimal) -> Decimal:
    """A23: max(2% of remaining balance, Rs 500)."""
    return q2(max(remaining * T.AMOUNT_TOL_PCT, T.AMOUNT_TOL_MIN))


def po_card(po: PORec, invoice_total: Decimal | None, match_type: str | None = None) -> dict[str, Any]:
    return {
        "po_number": po.po_number, "vendor_id": po.vendor_id, "status": po.status, "match_type": match_type,
        "total": po.total, "consumed": po.consumed, "remaining": po.remaining, "invoice_total": invoice_total,
        "remaining_after": po.remaining - invoice_total if invoice_total is not None else None,
    }


# ---------------------------------------------------------------------------
# PO inference scoring (A21)
# ---------------------------------------------------------------------------


def balance_fit(total: Decimal | None, po: PORec) -> float:
    if total is None:
        return 0.0
    remaining = po.remaining
    if total <= remaining + tolerance(remaining):
        return 1.0
    if remaining <= 0:
        return 0.0
    return max(0.0, 1.0 - float((total - remaining) / remaining))


def description_similarity(inv: NormalizedInvoice, po_lines: list[POLineRec]) -> float:
    descs = [li.description.lower() for li in inv.line_items if li.description]
    if not descs or not po_lines:
        return 0.0
    best = [max(fuzz.token_set_ratio(d, pl.description.lower()) for pl in po_lines) for d in descs]
    return sum(best) / len(best) / 100.0


def score_po(inv: NormalizedInvoice, po: PORec) -> dict[str, Any]:
    fit = balance_fit(inv.total, po)
    desc = description_similarity(inv, po.lines)
    score = T.PO_INFER_W_BALANCE * fit + T.PO_INFER_W_DESC * desc
    return {"po_number": po.po_number, "score": round(score, 3), "balance_fit": round(fit, 3),
            "description_similarity": round(desc, 3), "remaining": po.remaining}


def _explicit(inv: NormalizedInvoice, vendor: VendorMatch | None, pos: dict[str, PORec]) -> tuple[RuleResult, POMatch | None]:
    by_canon = {canonical_ref(n): po for n, po in pos.items()}
    po = by_canon.get(inv.po_reference_canonical)
    ref = inv.po_reference
    if po is None:
        return rule(S_PO, "PO-EXPLICIT", Outcome.FAIL, Severity.SOFT, f"PO {ref} on the invoice does not exist",
                    {"po_reference": ref}, review=True), None
    ev = {"po_reference": ref, "po_number": po.po_number, "po_vendor_id": po.vendor_id, "po_status": po.status}
    if vendor is None:
        return rule(S_PO, "PO-EXPLICIT", Outcome.FAIL, Severity.SOFT,
                    f"PO {po.po_number} exists but the vendor is unknown, so ownership cannot be confirmed",
                    ev, review=True), None
    if po.vendor_id != vendor.vendor.vendor_id:
        return rule(S_PO, "PO-EXPLICIT", Outcome.FAIL, Severity.SOFT,
                    f"PO {po.po_number} belongs to vendor {po.vendor_id}, not {vendor.vendor.vendor_id}",
                    ev, review=True), None
    if po.status != "OPEN":
        return rule(S_PO, "PO-EXPLICIT", Outcome.FAIL, Severity.SOFT, f"PO {po.po_number} is {po.status}",
                    ev, review=True), None
    return rule(S_PO, "PO-EXPLICIT", Outcome.PASS, Severity.SOFT,
                f"{po.po_number} found, open, and belongs to {vendor.vendor.legal_name}", ev), POMatch(po, "EXPLICIT")


def _infer(inv: NormalizedInvoice, vendor: VendorMatch | None, pos: dict[str, PORec]) -> tuple[RuleResult, POMatch | None, list[dict[str, Any]]]:
    if vendor is None:
        return rule(S_PO, "PO-INFER", Outcome.FAIL, Severity.SOFT,
                    "No PO reference on the invoice and no known vendor to infer one from", review=True), None, []
    open_pos = [po for po in pos.values() if po.vendor_id == vendor.vendor.vendor_id and po.status == "OPEN"]
    if not open_pos:
        return rule(S_PO, "PO-INFER", Outcome.FAIL, Severity.SOFT,
                    f"No PO reference on the invoice and {vendor.vendor.legal_name} has no open POs",
                    review=True), None, []
    scored = sorted((score_po(inv, po) for po in open_pos), key=lambda c: -c["score"])
    best = scored[0]
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    margin = best["score"] - second
    ev = {"candidates": scored, "min_score": T.PO_INFER_MIN_SCORE, "min_margin": T.PO_INFER_MIN_MARGIN}
    clear = best["score"] >= T.PO_INFER_MIN_SCORE and (len(scored) == 1 or margin >= T.PO_INFER_MIN_MARGIN)
    if clear:
        po = pos[best["po_number"]]
        next_best = f", next best {second:.2f}" if len(scored) > 1 else ""
        return rule(S_PO, "PO-INFER", Outcome.WARN, Severity.SOFT,
                    f"No PO on the invoice; inferred {po.po_number} (score {best['score']:.2f}{next_best})",
                    ev, review=True, flag=Flag.PO_INFERRED), POMatch(po, "INFERRED"), scored
    return rule(S_PO, "PO-INFER", Outcome.FAIL, Severity.SOFT,
                f"No PO on the invoice and no clear match among {len(scored)} open PO(s) "
                f"(best {best['po_number']} at {best['score']:.2f}, margin {margin:.2f})",
                ev, review=True), None, scored


def match_po(inv: NormalizedInvoice, vendor: VendorMatch | None, pos: dict[str, PORec]) -> tuple[StageResult, POMatch | None]:
    candidates: list[dict[str, Any]] = []
    if inv.po_reference_canonical:
        r, match = _explicit(inv, vendor, pos)
    else:
        r, match, candidates = _infer(inv, vendor, pos)
    payload: dict[str, Any] = {"po_reference": inv.po_reference, "candidates": candidates,
                               "po": po_card(match.po, inv.total, match.match_type) if match else None}
    return StageResult(stage=S_PO, message=r.message, payload=payload, rules=[r]), match


# ---------------------------------------------------------------------------
# Amount check
# ---------------------------------------------------------------------------


def _pair_line(desc: str, po_lines: list[POLineRec]) -> tuple[POLineRec | None, float]:
    best: tuple[float, float, POLineRec | None] = (0.0, 0.0, None)
    for pl in po_lines:
        a, b = desc.lower(), pl.description.lower()
        key = (fuzz.token_set_ratio(a, b), fuzz.ratio(a, b), pl)
        if key[:2] > best[:2]:
            best = key
    return (best[2], best[0]) if best[0] >= T.PO_LINE_PAIR_MIN else (None, best[0])


def check_unit_prices(inv: NormalizedInvoice, po: PORec) -> RuleResult:
    priced = [li for li in inv.line_items if li.unit_price is not None and li.description]
    if not priced or not po.lines:
        return skipped(S_AMT, "AMT-UNIT-PRICE", "No priced line items to compare")
    rate = (inv.tax_rate or T.DEFAULT_GST_RATE) if inv.tax_inclusive else Decimal("0")
    divisor = 1 + rate / 100
    rows: list[dict[str, Any]] = []
    flagged: list[str] = []
    for li in priced:
        assert li.unit_price is not None
        pl, sim = _pair_line(li.description, po.lines)
        if pl is None:
            rows.append({"description": li.description, "paired": None, "similarity": sim})
            continue
        unit = q2(li.unit_price / divisor)
        variance = (unit - pl.unit_price) / pl.unit_price if pl.unit_price else Decimal("0")
        over = abs(variance) > T.UNIT_PRICE_VARIANCE
        rows.append({"description": li.description, "paired": pl.description, "po_line_no": pl.line_no,
                     "invoice_unit_price": unit, "po_unit_price": pl.unit_price,
                     "variance_pct": float(round(variance * 100, 2)), "flagged": over})
        if over:
            flagged.append(f"{li.description[:40]} {float(variance * 100):+.1f}%")
    ev = {"lines": rows, "threshold_pct": float(T.UNIT_PRICE_VARIANCE * 100), "tax_inclusive_divisor": divisor}
    if flagged:
        return rule(S_AMT, "AMT-UNIT-PRICE", Outcome.WARN, Severity.INFO,
                    f"Unit price differs from PO by more than {T.UNIT_PRICE_VARIANCE * 100:.0f}%: {'; '.join(flagged)}", ev)
    return rule(S_AMT, "AMT-UNIT-PRICE", Outcome.PASS, Severity.INFO,
                f"Unit prices within {T.UNIT_PRICE_VARIANCE * 100:.0f}% of the PO", ev)


def check_amount(inv: NormalizedInvoice, match: POMatch | None) -> StageResult:
    if match is None:
        return StageResult(stage=S_AMT, message="No PO matched, nothing to compare against", skipped=True,
                           rules=[skipped(S_AMT, "AMT-REMAINING", "No PO matched"),
                                  skipped(S_AMT, "AMT-UNIT-PRICE", "No PO matched")])
    po = match.po
    if inv.total is None:
        return StageResult(stage=S_AMT, message="Invoice total missing", skipped=True,
                           payload={"po": po_card(po, None, match.match_type)},
                           rules=[skipped(S_AMT, "AMT-REMAINING", "Invoice total missing"), check_unit_prices(inv, po)])
    remaining = po.remaining
    tol = tolerance(remaining)
    over = inv.total - remaining
    ev = {"po_number": po.po_number, "po_total": po.total, "consumed": po.consumed, "remaining": remaining,
          "invoice_total": inv.total, "tolerance": tol, "overage": max(over, Decimal("0.00"))}
    if over <= 0:
        r = rule(S_AMT, "AMT-REMAINING", Outcome.PASS, Severity.SOFT,
                 f"Invoice {inr(inv.total)} is within the remaining PO balance of {inr(remaining)}", ev)
    elif over <= tol:
        r = rule(S_AMT, "AMT-REMAINING", Outcome.PASS, Severity.SOFT,
                 f"Within tolerance: invoice {inr(inv.total)} exceeds remaining {inr(remaining)} by {inr(over)} "
                 f"({float(over / remaining * 100) if remaining > 0 else 0:.1f}%, tolerance {inr(tol)})", ev)
    else:
        r = rule(S_AMT, "AMT-REMAINING", Outcome.FAIL, Severity.SOFT,
                 f"Invoice {inr(inv.total)} exceeds remaining {inr(remaining)} by {inr(over)}",
                 ev, review=True, flag=Flag.OVER_PO)
    unit = check_unit_prices(inv, po)
    return StageResult(stage=S_AMT, message=r.message, rules=[r, unit],
                       payload={"po": po_card(po, inv.total, match.match_type), "tolerance": tol,
                                "overage": ev["overage"], "unit_prices": unit.evidence.get("lines", [])})
