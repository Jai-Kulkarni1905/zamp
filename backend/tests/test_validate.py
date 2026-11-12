from datetime import date

from app.pipeline.stages.ingest import read_pdf
from app.pipeline.stages.validate import validate
from app.schemas import Flag, Outcome, Severity
from tests.conftest import INVOICES
from tests.factories import EC3, HP2, make_inv, tf
from app.pipeline.stages.normalize import normalize


def _rules(inv, today: date, text: str = "", scanned: bool = True):  # type: ignore[no-untyped-def]
    return {r.rule_id: r for r in validate(inv, is_scanned=scanned, pdf_text=text, today=today).rules}


def test_clean_invoice_passes(today: date) -> None:
    _, text = read_pdf((INVOICES / "HP-1.pdf").read_bytes())
    rules = _rules(make_inv(), today, text, scanned=False)
    assert all(r.outcome == Outcome.PASS for r in rules.values()), [r.message for r in rules.values()]


def test_missing_invoice_number_is_soft_fail_with_low_confidence(today: date) -> None:
    rules = _rules(make_inv(invoice_number=tf(None)), today)
    r = rules["VAL-REQUIRED"]
    assert (r.outcome, r.severity, r.flag, r.review_reason) == (Outcome.FAIL, Severity.SOFT, Flag.LOW_CONFIDENCE, True)
    assert r.evidence["missing"] == ["invoice_number"]


def test_low_confidence_warns(today: date) -> None:
    rules = _rules(make_inv(total=tf("177000.00", 0.55)), today)
    r = rules["VAL-CONFIDENCE"]
    assert r.outcome == Outcome.WARN and r.review_reason and r.flag == Flag.LOW_CONFIDENCE
    assert "total" in r.evidence["low_fields"]


def test_grounding_skipped_for_scanned_and_warns_on_miss(today: date) -> None:
    assert _rules(make_inv(), today, scanned=True)["VAL-GROUNDING"].outcome == Outcome.SKIPPED
    _, text = read_pdf((INVOICES / "HP-1.pdf").read_bytes())
    r = _rules(make_inv(total="187000.00", subtotal="160000.00"), today, text, scanned=False)["VAL-GROUNDING"]
    assert r.outcome == Outcome.WARN and r.evidence["total_found"] is False


def test_grounding_matches_reformatted_invoice_number(today: date) -> None:
    _, text = read_pdf((INVOICES / "EC-2.pdf").read_bytes())
    r = _rules(make_inv(invoice_number="INV-2026-142"), today, text, scanned=False)["VAL-GROUNDING"]
    assert r.outcome == Outcome.PASS


def test_arithmetic_tolerance(today: date) -> None:
    assert _rules(make_inv(total="177000.90"), today)["VAL-ARITH-TOTAL"].outcome == Outcome.PASS
    r = _rules(make_inv(total="177002.00"), today)["VAL-ARITH-TOTAL"]
    assert r.outcome == Outcome.FAIL and r.severity == Severity.SOFT
    assert _rules(make_inv(subtotal="149000.00", total="176000.00"), today)["VAL-ARITH-LINES"].outcome == Outcome.FAIL


def test_tax_inclusive_arithmetic(today: date) -> None:
    _, inv = normalize(HP2)
    rules = _rules(inv, today)
    assert rules["VAL-ARITH-LINES"].outcome == Outcome.PASS
    assert rules["VAL-ARITH-TOTAL"].outcome == Outcome.SKIPPED


def test_dates(today: date) -> None:
    assert _rules(make_inv(invoice_date="2026-11-20"), today)["VAL-DATE-FUTURE"].outcome == Outcome.FAIL
    stale = _rules(make_inv(invoice_date="2026-04-01", due_date="2026-05-01"), today)["VAL-DATE-STALE"]
    assert stale.outcome == Outcome.WARN and stale.review_reason
    due = _rules(make_inv(due_date="2026-10-01"), today)["VAL-DUE-DATE"]
    assert due.outcome == Outcome.WARN and due.severity == Severity.INFO and not due.review_reason


def test_gstin_and_currency(today: date) -> None:
    assert _rules(make_inv(vendor_gstin="27AAKCS4821M1"), today)["VAL-GSTIN-FORMAT"].outcome == Outcome.WARN
    assert _rules(make_inv(currency="USD"), today)["VAL-CURRENCY"].outcome == Outcome.FAIL


def test_ec3_scanned_missing_number(today: date) -> None:
    _, inv = normalize(EC3)
    rules = _rules(inv, today)
    assert rules["VAL-REQUIRED"].outcome == Outcome.FAIL
    assert rules["VAL-CONFIDENCE"].outcome == Outcome.WARN  # invoice date read at 0.66
    assert rules["VAL-GROUNDING"].outcome == Outcome.SKIPPED
