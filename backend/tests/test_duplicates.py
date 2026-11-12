from datetime import date
from decimal import Decimal

from app.pipeline.stages.duplicates import check_duplicates
from app.schemas import Flag, Outcome, PriorRun, Severity
from tests.factories import make_inv


def prior(**kw: object) -> PriorRun:
    base: dict[str, object] = dict(run_id="r1", filename="HP-1.pdf", file_hash="aaa", vendor_key="V:V001",
                                   invoice_number="INV-2026-142", invoice_number_canonical="INV2026142",
                                   invoice_date=date(2026, 10, 23), total=Decimal("177000.00"))
    base.update(kw)
    return PriorRun(**base)  # type: ignore[arg-type]


def _rules(inv, prior_runs, file_hash="bbb", key="V:V001"):  # type: ignore[no-untyped-def]
    return {r.rule_id: r for r in check_duplicates(file_hash, inv, key, prior_runs).rules}


def test_no_prior_runs() -> None:
    rules = _rules(make_inv(), [])
    assert all(r.outcome == Outcome.PASS for r in rules.values())


def test_same_file_hash() -> None:
    r = _rules(make_inv(), [prior()], file_hash="aaa")["DUP-HASH"]
    assert (r.outcome, r.severity, r.flag) == (Outcome.FAIL, Severity.HARD, Flag.DUPLICATE)
    assert r.evidence["original_run_id"] == "r1"


def test_ec2_reformatted_number_is_duplicate() -> None:
    rules = _rules(make_inv(invoice_number="INV/2026/0142"), [prior()])
    assert rules["DUP-HASH"].outcome == Outcome.PASS
    assert rules["DUP-NUMBER"].outcome == Outcome.FAIL
    assert rules["DUP-NUMBER"].evidence["original_filename"] == "HP-1.pdf"
    assert rules["DUP-FUZZY"].outcome == Outcome.FAIL  # second line of defence


def test_fuzzy_duplicate_near_number() -> None:
    rules = _rules(make_inv(invoice_number="INV-2026-1420", invoice_date="2026-10-27"), [prior()])
    assert rules["DUP-NUMBER"].outcome == Outcome.PASS
    assert rules["DUP-FUZZY"].outcome == Outcome.FAIL


def test_fuzzy_needs_all_conditions() -> None:
    far_date = _rules(make_inv(invoice_number="INV-2026-1420", invoice_date="2026-11-05"), [prior()])
    assert far_date["DUP-FUZZY"].outcome == Outcome.PASS
    other_total = _rules(make_inv(invoice_number="INV-2026-1420", total="177002.00", subtotal="150002.00"), [prior()])
    assert other_total["DUP-FUZZY"].outcome == Outcome.PASS


def test_same_number_other_vendor_is_not_duplicate() -> None:
    rules = _rules(make_inv(), [prior(vendor_key="V:V002")])
    assert rules["DUP-NUMBER"].outcome == Outcome.PASS and rules["DUP-FUZZY"].outcome == Outcome.PASS


def test_missing_number_skips_number_checks() -> None:
    rules = _rules(make_inv(invoice_number=None), [prior()])
    assert rules["DUP-NUMBER"].outcome == Outcome.SKIPPED and rules["DUP-FUZZY"].outcome == Outcome.SKIPPED
