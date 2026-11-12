from app.pipeline.stages.normalize import normalize
from app.pipeline.stages.vendor import check_vendor, vendor_key
from app.schemas import Flag, Outcome, Severity, VendorRec
from tests.factories import EC4, make_inv


def _rules(inv, vendors):  # type: ignore[no-untyped-def]
    result, match = check_vendor(inv, vendors)
    return {r.rule_id: r for r in result.rules}, match


def test_match_by_gstin(vendors: list[VendorRec]) -> None:
    rules, m = _rules(make_inv(vendor_name="Some Other Name"), vendors)
    assert m is not None and m.vendor.vendor_id == "V001" and m.method == "GSTIN"
    assert all(r.outcome == Outcome.PASS for r in rules.values())


def test_match_by_fuzzy_alias(vendors: list[VendorRec]) -> None:
    rules, m = _rules(make_inv(vendor_gstin=None, vendor_name="SHAKTI INDUSTRIAL SUPPLIES PRIVATE LIMITED"), vendors)
    assert m is not None and m.vendor.vendor_id == "V001" and m.method == "NAME"
    assert rules["VEN-GSTIN"].outcome == Outcome.SKIPPED


def test_name_match_with_different_gstin_warns(vendors: list[VendorRec]) -> None:
    rules, m = _rules(make_inv(vendor_gstin="27AAKCS9999M1Z5"), vendors)
    assert m is not None and m.method == "NAME"
    assert rules["VEN-GSTIN"].outcome == Outcome.WARN and rules["VEN-GSTIN"].review_reason


def test_unknown_vendor_is_soft(vendors: list[VendorRec]) -> None:
    rules, m = _rules(make_inv(vendor_gstin=None, vendor_name="Totally New Traders"), vendors)
    assert m is None
    assert (rules["VEN-MATCH"].outcome, rules["VEN-MATCH"].severity) == (Outcome.FAIL, Severity.SOFT)
    assert rules["VEN-STATUS"].outcome == Outcome.SKIPPED


def test_blocked_vendor_is_hard(vendors: list[VendorRec]) -> None:
    rules, _ = _rules(make_inv(vendor_name="Apex Chemicals Trading Co", vendor_gstin="07AAOFA3318D1ZQ",
                               bank_account="2111234567", ifsc="KKBK0000211"), vendors)
    assert (rules["VEN-STATUS"].outcome, rules["VEN-STATUS"].severity) == (Outcome.FAIL, Severity.HARD)


def test_bank_change_is_fraud_risk(vendors: list[VendorRec]) -> None:
    _, inv = normalize(EC4)
    rules, _ = _rules(inv, vendors)
    r = rules["VEN-BANK"]
    assert (r.outcome, r.severity, r.flag, r.review_reason) == (Outcome.FAIL, Severity.SOFT, Flag.FRAUD_RISK, True)
    assert r.evidence["phone_on_file"] == "+91 40 6712 5500"
    assert "2345" in r.message and "1234" in r.message  # masked accounts, last 4 only
    assert "045661900002345" not in r.message


def test_missing_bank_details_is_info_only(vendors: list[VendorRec]) -> None:
    rules, _ = _rules(make_inv(bank_account=None, ifsc=None), vendors)
    assert rules["VEN-BANK"].outcome == Outcome.SKIPPED
    assert rules["VEN-BANK-MISSING"].outcome == Outcome.WARN
    assert rules["VEN-BANK-MISSING"].severity == Severity.INFO and not rules["VEN-BANK-MISSING"].review_reason


def test_vendor_key(vendors: list[VendorRec]) -> None:
    inv = make_inv()
    _, m = check_vendor(inv, vendors)
    assert vendor_key(inv, m) == "V:V001"
    assert vendor_key(make_inv(vendor_gstin="29ABCDE1234F1Z5", vendor_name="X"), None) == "G:29ABCDE1234F1Z5"
