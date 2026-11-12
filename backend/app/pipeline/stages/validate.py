"""Stage 4: data quality. Required fields, confidence, grounding, arithmetic, dates, GSTIN, currency."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.config import T
from app.money import canonical_ref, inr, is_valid_gstin, numbers_in_text
from app.pipeline.stages._rules import FIELD_LABELS, rule, skipped
from app.schemas import (
    REQUIRED_FIELDS,
    Flag,
    NormalizedInvoice,
    Outcome,
    RuleResult,
    Severity,
    Stage,
    StageResult,
)

S = Stage.VALIDATE


def _labels(fields: list[str]) -> str:
    return ", ".join(FIELD_LABELS.get(f, f.replace("_", " ")) for f in fields)


def line_sum(inv: NormalizedInvoice) -> Decimal | None:
    """Sum of line amounts, computing qty x unit_price where the amount is missing. None if unknowable."""
    if not inv.line_items:
        return None
    total = Decimal("0.00")
    for li in inv.line_items:
        if li.amount is not None:
            total += li.amount
        elif li.qty is not None and li.unit_price is not None:
            total += li.qty * li.unit_price
        else:
            return None
    return total


def invoice_number_in_text(number: str, text: str) -> bool:
    """A13: canonical form matches 1 to 3 consecutive tokens, or the raw number appears ignoring punctuation."""
    target = canonical_ref(number)
    if not target:
        return False
    tokens = text.split()
    for size in (1, 2, 3):
        for i in range(len(tokens) - size + 1):
            if canonical_ref(" ".join(tokens[i:i + size])) == target:
                return True
    squash = re.sub(r"[^A-Z0-9]", "", text.upper())
    return re.sub(r"[^A-Z0-9]", "", number.upper()) in squash


def check_required(inv: NormalizedInvoice) -> tuple[RuleResult, list[str]]:
    missing = [f for f in REQUIRED_FIELDS if getattr(inv, f) in (None, "")]
    if missing:
        return rule(S, "VAL-REQUIRED", Outcome.FAIL, Severity.SOFT, f"Missing required field: {_labels(missing)}",
                    {"missing": missing}, review=True, flag=Flag.LOW_CONFIDENCE), missing
    return rule(S, "VAL-REQUIRED", Outcome.PASS, Severity.SOFT, "All required fields present"), missing


def check_confidence(inv: NormalizedInvoice, missing: list[str]) -> RuleResult:
    low = {f: inv.confidence.get(f, 1.0) for f in REQUIRED_FIELDS
           if f not in missing and inv.confidence.get(f, 1.0) < T.LOW_CONFIDENCE}
    if low:
        detail = ", ".join(f"{FIELD_LABELS[f]} {c:.2f}" for f, c in low.items())
        return rule(S, "VAL-CONFIDENCE", Outcome.WARN, Severity.SOFT,
                    f"Low extraction confidence: {detail} (below {T.LOW_CONFIDENCE:.2f})",
                    {"low_fields": low, "threshold": T.LOW_CONFIDENCE}, review=True, flag=Flag.LOW_CONFIDENCE)
    return rule(S, "VAL-CONFIDENCE", Outcome.PASS, Severity.SOFT, "Required fields read with high confidence",
                {"confidence": {f: inv.confidence.get(f) for f in REQUIRED_FIELDS}})


def check_grounding(inv: NormalizedInvoice, is_scanned: bool, pdf_text: str) -> RuleResult:
    if is_scanned:
        return skipped(S, "VAL-GROUNDING", "Scanned PDF: no text layer to check extracted values against")
    if inv.total is None and not inv.invoice_number:
        return skipped(S, "VAL-GROUNDING", "Nothing to check: total and invoice number both missing")
    evidence: dict[str, object] = {}
    misses: list[str] = []
    if inv.total is not None:
        found = inv.total in numbers_in_text(pdf_text)
        evidence["total_found"] = found
        if not found:
            misses.append(f"total {inr(inv.total)}")
    if inv.invoice_number:
        found = invoice_number_in_text(inv.invoice_number, pdf_text)
        evidence["invoice_number_found"] = found
        if not found:
            misses.append(f"invoice number {inv.invoice_number}")
    if misses:
        return rule(S, "VAL-GROUNDING", Outcome.WARN, Severity.SOFT,
                    f"Not found in the PDF text: {', '.join(misses)}", evidence, review=True, flag=Flag.LOW_CONFIDENCE)
    return rule(S, "VAL-GROUNDING", Outcome.PASS, Severity.SOFT,
                "Total and invoice number found verbatim in the PDF text", evidence)


def check_arithmetic(inv: NormalizedInvoice) -> list[RuleResult]:
    tol = T.ARITH_TOLERANCE
    lines = line_sum(inv)
    out: list[RuleResult] = []

    if inv.tax_inclusive:
        if lines is None or inv.total is None:
            out.append(skipped(S, "VAL-ARITH-LINES", "Line amounts or total missing"))
        else:
            diff = lines - inv.total
            ok = abs(diff) <= tol
            out.append(rule(S, "VAL-ARITH-LINES", Outcome.PASS if ok else Outcome.FAIL, Severity.SOFT,
                            f"Tax-inclusive lines {inr(lines)} {'match' if ok else 'do not match'} total {inr(inv.total)}"
                            + ("" if ok else f" (difference {inr(diff)})"),
                            {"line_sum": lines, "total": inv.total, "difference": diff, "tolerance": tol}, review=True))
        out.append(skipped(S, "VAL-ARITH-TOTAL", "Tax-inclusive pricing: taxes are already inside the line amounts"))
        return out

    if lines is None or inv.subtotal is None:
        out.append(skipped(S, "VAL-ARITH-LINES", "Line amounts or subtotal missing"))
    else:
        diff = lines - inv.subtotal
        ok = abs(diff) <= tol
        out.append(rule(S, "VAL-ARITH-LINES", Outcome.PASS if ok else Outcome.FAIL, Severity.SOFT,
                        f"Line items add up to {inr(lines)}, subtotal is {inr(inv.subtotal)}"
                        + ("" if ok else f" (difference {inr(diff)})"),
                        {"line_sum": lines, "subtotal": inv.subtotal, "difference": diff, "tolerance": tol}, review=True))

    if inv.subtotal is None or inv.total is None:
        out.append(skipped(S, "VAL-ARITH-TOTAL", "Subtotal or total missing"))
    else:
        tax = inv.tax_total or Decimal("0.00")
        expected = inv.subtotal + tax
        diff = expected - inv.total
        ok = abs(diff) <= tol
        out.append(rule(S, "VAL-ARITH-TOTAL", Outcome.PASS if ok else Outcome.FAIL, Severity.SOFT,
                        f"Subtotal {inr(inv.subtotal)} + tax {inr(tax)} = {inr(expected)}, total is {inr(inv.total)}"
                        + ("" if ok else f" (difference {inr(diff)})"),
                        {"subtotal": inv.subtotal, "tax": tax, "expected_total": expected, "total": inv.total,
                         "difference": diff, "tolerance": tol}, review=True))
    return out


def check_dates(inv: NormalizedInvoice, today: date) -> list[RuleResult]:
    if inv.invoice_date is None:
        return [skipped(S, "VAL-DATE-FUTURE", "No invoice date"), skipped(S, "VAL-DATE-STALE", "No invoice date"),
                skipped(S, "VAL-DUE-DATE", "No invoice date")]
    d = inv.invoice_date
    age = (today - d).days
    out = [
        rule(S, "VAL-DATE-FUTURE", Outcome.FAIL if d > today else Outcome.PASS, Severity.SOFT,
             f"Invoice date {d.isoformat()} is in the future (today {today.isoformat()})" if d > today
             else f"Invoice date {d.isoformat()} is not in the future",
             {"invoice_date": d, "today": today}, review=True),
        rule(S, "VAL-DATE-STALE", Outcome.WARN if age > T.MAX_INVOICE_AGE_DAYS else Outcome.PASS, Severity.SOFT,
             f"Invoice is {age} days old (limit {T.MAX_INVOICE_AGE_DAYS})",
             {"age_days": age, "limit_days": T.MAX_INVOICE_AGE_DAYS}, review=True),
    ]
    if inv.due_date is None:
        out.append(skipped(S, "VAL-DUE-DATE", "No due date"))
    else:
        bad = inv.due_date < d
        out.append(rule(S, "VAL-DUE-DATE", Outcome.WARN if bad else Outcome.PASS, Severity.INFO,
                        f"Due date {inv.due_date.isoformat()} is before invoice date" if bad
                        else f"Due date {inv.due_date.isoformat()} is after invoice date",
                        {"invoice_date": d, "due_date": inv.due_date}))
    return out


def check_gstin(inv: NormalizedInvoice) -> RuleResult:
    if not inv.vendor_gstin:
        return skipped(S, "VAL-GSTIN-FORMAT", "No GSTIN on the invoice")
    ok = is_valid_gstin(inv.vendor_gstin)
    return rule(S, "VAL-GSTIN-FORMAT", Outcome.PASS if ok else Outcome.WARN, Severity.SOFT,
                f"GSTIN {inv.vendor_gstin} has a valid format" if ok else f"GSTIN {inv.vendor_gstin} has an invalid format",
                {"gstin": inv.vendor_gstin}, review=True)


def check_currency(inv: NormalizedInvoice) -> RuleResult:
    ok = inv.currency == "INR"
    return rule(S, "VAL-CURRENCY", Outcome.PASS if ok else Outcome.FAIL, Severity.SOFT,
                "Currency is INR" if ok else f"Currency is {inv.currency}, all POs are in INR",
                {"currency": inv.currency}, review=True)


def validate(inv: NormalizedInvoice, *, is_scanned: bool, pdf_text: str, today: date) -> StageResult:
    required, missing = check_required(inv)
    rules = [
        required,
        check_confidence(inv, missing),
        check_grounding(inv, is_scanned, pdf_text),
        *check_arithmetic(inv),
        *check_dates(inv, today),
        check_gstin(inv),
        check_currency(inv),
    ]
    failed = [r for r in rules if r.outcome in (Outcome.FAIL, Outcome.WARN)]
    message = "All data quality checks passed" if not failed else f"{len(failed)} issue(s): " + "; ".join(
        r.message for r in failed[:2]) + ("..." if len(failed) > 2 else "")
    return StageResult(stage=S, message=message, payload={"checks": [r.model_dump(mode="json") for r in rules]},
                       rules=rules)
