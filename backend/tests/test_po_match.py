from decimal import Decimal

from app.pipeline.stages.normalize import normalize
from app.pipeline.stages.po_match import check_amount, match_po, tolerance
from app.pipeline.stages.vendor import check_vendor
from app.schemas import Flag, Outcome, PORec, Severity, StageStatus, VendorRec
from tests.factories import EC1_C, EC3, HP2, make_inv


def _match(inv, vendors, pos):  # type: ignore[no-untyped-def]
    _, vm = check_vendor(inv, vendors)
    result, pm = match_po(inv, vm, pos)
    return result, pm


def test_tolerance() -> None:
    assert tolerance(Decimal("200600")) == Decimal("4012.00")
    assert tolerance(Decimal("60000")) == Decimal("1200.00")
    assert tolerance(Decimal("10000")) == Decimal("500.00")
    assert tolerance(Decimal("0")) == Decimal("500.00")


def test_explicit_po(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    result, pm = _match(make_inv(po_reference="PO/2026/101"), vendors, pos)
    assert pm is not None and pm.po.po_number == "PO-2026-0101" and pm.match_type == "EXPLICIT"
    assert result.status == StageStatus.PASS


def test_explicit_po_other_vendor_closed_or_missing(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    for ref, text in [("PO-2026-0103", "belongs to vendor V003"), ("PO-2026-0107", "CLOSED"),
                      ("PO-2026-9999", "does not exist")]:
        result, pm = _match(make_inv(po_reference=ref), vendors, pos)
        r = result.rules[0]
        assert pm is None and r.outcome == Outcome.FAIL and r.severity == Severity.SOFT and text in r.message


def test_infer_po_clear_winner(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    _, inv = normalize(EC3)
    result, pm = _match(inv, vendors, pos)
    r = result.rules[0]
    assert pm is not None and pm.po.po_number == "PO-2026-0104" and pm.match_type == "INFERRED"
    assert (r.rule_id, r.outcome, r.flag, r.review_reason) == ("PO-INFER", Outcome.WARN, Flag.PO_INFERRED, True)
    scores = {c["po_number"]: c["score"] for c in r.evidence["candidates"]}
    assert scores["PO-2026-0104"] >= 0.75 and scores["PO-2026-0104"] - scores["PO-2026-0105"] >= 0.15


def test_infer_po_ambiguous(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    # Vague description and an amount that fits both open POs of V004: no clear winner.
    _, inv = normalize(EC3.model_copy(update={"line_items": []}))
    result, pm = _match(inv, vendors, pos)
    assert pm is None and result.rules[0].outcome == Outcome.FAIL


def test_amount_exact_match(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    inv = make_inv()
    _, pm = _match(inv, vendors, pos)
    r = {x.rule_id: x for x in check_amount(inv, pm).rules}
    assert r["AMT-REMAINING"].outcome == Outcome.PASS
    assert r["AMT-UNIT-PRICE"].outcome == Outcome.PASS


def test_hp2_within_tolerance_tax_inclusive(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    _, inv = normalize(HP2)
    _, pm = _match(inv, vendors, pos)
    r = {x.rule_id: x for x in check_amount(inv, pm).rules}
    assert r["AMT-REMAINING"].outcome == Outcome.PASS
    assert r["AMT-REMAINING"].message.startswith("Within tolerance")
    assert r["AMT-UNIT-PRICE"].outcome == Outcome.PASS  # GST backed out of inclusive prices (A36)


def test_ec1c_over_remaining_balance(vendors: list[VendorRec], pos: dict[str, PORec]) -> None:
    po = pos["PO-2026-0103"].model_copy(update={"consumed": Decimal("240000.00")})
    _, inv = normalize(EC1_C)
    _, pm = _match(inv, vendors, {**pos, "PO-2026-0103": po})
    r = {x.rule_id: x for x in check_amount(inv, pm).rules}
    amt = r["AMT-REMAINING"]
    assert (amt.outcome, amt.severity, amt.flag) == (Outcome.FAIL, Severity.SOFT, Flag.OVER_PO)
    assert "exceeds remaining ₹60,000.00 by ₹30,000.00" in amt.message
    assert r["AMT-UNIT-PRICE"].outcome == Outcome.WARN and r["AMT-UNIT-PRICE"].severity == Severity.INFO


def test_amount_skipped_without_po() -> None:
    result = check_amount(make_inv(), None)
    assert result.status == StageStatus.SKIPPED
