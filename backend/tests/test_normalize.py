from datetime import date
from decimal import Decimal

import pytest

from app.money import canonical_ref, inr, parse_amount
from app.pipeline.stages.normalize import normalize, parse_date
from app.schemas import Outcome
from tests.factories import make_extraction, tf


@pytest.mark.parametrize(("a", "b"), [
    ("INV/2026/0142", "INV-2026-142"),
    ("inv 2026 142", "INV-2026-0142"),
    ("PO-2026-0101", "PO/2026/101"),
    ("VSF/2627/0311", "vsf-2627-311"),
])
def test_canonical_numbers_match(a: str, b: str) -> None:
    assert canonical_ref(a) == canonical_ref(b)


def test_canonical_number_details() -> None:
    assert canonical_ref("INV/2026/0142") == "INV2026142"
    assert canonical_ref("000") == "0"
    assert canonical_ref("INV-2026-142") != canonical_ref("INV-2026-143")
    assert canonical_ref(None) is None
    assert canonical_ref("--") is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("Rs. 1,77,000.00", "177000.00"),
    ("INR 90,000", "90000.00"),
    ("₹ 1,20,000", "120000.00"),
    ("(500.00)", "-500.00"),
    ("-0.01", "-0.01"),
    ("2,03,610.005", "203610.01"),
    ("n/a", None),
    (None, None),
])
def test_parse_amount(raw: str | None, expected: str | None) -> None:
    value = parse_amount(raw)
    assert (str(value) if value is not None else None) == expected
    if value is not None:
        assert isinstance(value, Decimal)


@pytest.mark.parametrize(("raw", "expected"), [
    ("2026-10-23", date(2026, 10, 23)),
    ("23-Oct-2026", date(2026, 10, 23)),
    ("07/11/2026", date(2026, 11, 7)),  # day first (Indian format)
    ("31 October 2026", date(2026, 10, 31)),
    ("2nd November 2026", date(2026, 11, 2)),
    ("not a date", None),
])
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_indian_grouping() -> None:
    assert inr(Decimal("177000")) == "₹1,77,000.00"
    assert inr(Decimal("12345678.5")) == "₹1,23,45,678.50"
    assert inr(Decimal("500")) == "₹500.00"
    assert inr(Decimal("-30000")) == "-₹30,000.00"


def test_normalize_hp1() -> None:
    result, inv = normalize(make_extraction(vendor_gstin="27aakcs 4821m1z5", ifsc="hdfc0001234"))
    assert inv.total == Decimal("177000.00")
    assert inv.subtotal == Decimal("150000.00")
    assert inv.tax_total == Decimal("27000.00")
    assert inv.invoice_number_canonical == "INV2026142"
    assert inv.po_reference_canonical == "PO2026101"
    assert inv.vendor_gstin == "27AAKCS4821M1Z5"
    assert inv.ifsc == "HDFC0001234"
    assert inv.invoice_date == date(2026, 10, 23)
    assert result.rules[0].outcome == Outcome.PASS


def test_normalize_unparseable_value_is_missing_and_warned() -> None:
    result, inv = normalize(make_extraction(invoice_date="sometime soon"))
    assert inv.invoice_date is None
    assert result.rules[0].outcome == Outcome.WARN
    assert result.rules[0].evidence["unparsed"][0]["field"] == "invoice_date"


def test_missing_currency_assumed_inr() -> None:
    _, inv = normalize(make_extraction(currency=tf(None)))
    assert inv.currency == "INR"
    _, inv = normalize(make_extraction(currency="Rs."))
    assert inv.currency == "INR"
    _, inv = normalize(make_extraction(currency="USD"))
    assert inv.currency == "USD"
