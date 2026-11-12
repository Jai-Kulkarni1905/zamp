"""PLAN.md section 7 edge cases, on the REAL recorded Gemini extractions in data/fixtures (fixture mode,
no API calls). Each EC runs in its own demo order from a fresh in-memory DB, plus variants that prove the
behaviour comes from the rules and not from the test data."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app import repo
from app.config import ROOT, Settings
from app.models import Run
from app.pipeline.events import EventBus
from app.pipeline.runner import create_run, process_run
from tests.conftest import INVOICES

DEMO_ORDER = ["HP-1", "HP-2", "EC-1-A", "EC-1-B", "EC-1-C", "EC-2", "EC-3", "EC-4"]


@pytest.fixture
def real(settings: Settings, tmp_path: Path) -> Settings:
    """Real recorded extractions, read-only (fixture mode never writes), isolated uploads."""
    return dataclasses.replace(settings, fixtures_dir=ROOT / "data" / "fixtures", llm_mode="fixture")


def run(session: Session, settings: Settings, name: str) -> Run:
    pdf = INVOICES / f"{name}.pdf"
    created = create_run(session, pdf.name, pdf.read_bytes(), settings)
    done = process_run(session, created.id, bus=EventBus(), settings=settings)
    assert done.status == "DONE", done.error
    return done


def rules_of(run_: Run) -> dict[str, tuple[str, str]]:
    return {r.rule_id: (r.outcome, r.message) for r in run_.rules}


def test_real_fixtures_exist_for_every_test_pdf(real: Settings) -> None:
    from app.llm.gemini import fixture_path
    from app.pipeline.stages.ingest import sha256

    missing = [n for n in DEMO_ORDER if not fixture_path(sha256((INVOICES / f"{n}.pdf").read_bytes()), real).exists()]
    assert missing == [], f"record fixtures for {missing} (python -m app.cli record-fixtures)"


# -- EC-1: split PO ---------------------------------------------------------------------------


def test_ec1_split_po_third_invoice_exceeds_remaining(session: Session, real: Settings) -> None:
    a, b = run(session, real, "EC-1-A"), run(session, real, "EC-1-B")
    assert (a.decision, b.decision) == ("APPROVED", "APPROVED")
    assert repo.consumed_by_po(session)["PO-2026-0103"] == Decimal("240000.00")

    c = run(session, real, "EC-1-C")
    assert (c.decision, c.flags) == ("NEEDS_REVIEW", ["OVER_PO"])
    outcome, message = rules_of(c)["AMT-REMAINING"]
    assert outcome == "FAIL" and "exceeds remaining ₹60,000.00 by ₹30,000.00" in message
    assert c.explanation_json["verdict"].startswith("Needs review: Invoice ₹90,000.00 exceeds remaining ₹60,000.00")
    assert any("amend PO-2026-0103" in a for a in c.explanation_json["next_actions"])
    # C waits for review, so it consumes nothing yet.
    assert repo.consumed_by_po(session)["PO-2026-0103"] == Decimal("240000.00")


def test_ec1_variant_c_fits_when_b_is_rejected_by_reviewer(session: Session, real: Settings) -> None:
    run(session, real, "EC-1-A")
    b = run(session, real, "EC-1-B")
    b.reviewer_action, b.reviewer_note = "REJECT", "Duplicate milestone billing"
    session.commit()  # B no longer counts: remaining is ₹1,80,000

    c = run(session, real, "EC-1-C")
    assert c.decision == "APPROVED" and "OVER_PO" not in c.flags


# -- EC-2: disguised duplicate -----------------------------------------------------------------


def test_ec2_disguised_duplicate_is_rejected_and_links_original(session: Session, real: Settings) -> None:
    hp1 = run(session, real, "HP-1")
    ec2 = run(session, real, "EC-2")
    assert hp1.file_hash != ec2.file_hash  # different file, different layout
    assert (hp1.invoice_number, ec2.invoice_number) == ("INV-2026-142", "INV/2026/0142")
    assert hp1.invoice_number_canonical == ec2.invoice_number_canonical == "INV2026142"

    assert (ec2.decision, ec2.flags) == ("REJECTED", ["DUPLICATE"])
    dup = next(r for r in ec2.rules if r.rule_id == "DUP-NUMBER")
    assert dup.outcome == "FAIL" and dup.evidence_json["original_run_id"] == hp1.id
    assert ec2.explanation_json["next_actions"] == ["Do not pay. Compare with the original run (HP-1.pdf)"]
    # The PO overage is still recorded, only not flagged (A42).
    assert rules_of(ec2)["AMT-REMAINING"][0] == "FAIL"


def test_ec2_variant_alone_is_a_normal_invoice(session: Session, real: Settings) -> None:
    ec2 = run(session, real, "EC-2")  # nothing earlier to duplicate
    assert (ec2.decision, ec2.flags) == ("APPROVED", [])


# -- EC-3: scanned + missing data ---------------------------------------------------------------


def test_ec3_scanned_missing_number_and_po_needs_review(session: Session, real: Settings) -> None:
    ec3 = run(session, real, "EC-3")
    assert ec3.decision == "NEEDS_REVIEW"
    assert set(ec3.flags) == {"LOW_CONFIDENCE", "PO_INFERRED"}
    assert ec3.invoice_number is None
    assert (ec3.matched_po, ec3.po_match_type) == ("PO-2026-0104", "INFERRED")

    r = rules_of(ec3)
    assert r["VAL-REQUIRED"][0] == "FAIL" and "invoice number" in r["VAL-REQUIRED"][1]
    assert r["VAL-GROUNDING"][0] == "SKIPPED"  # no text layer to ground against
    assert r["PO-INFER"][0] == "WARN"
    candidates = next(x for x in ec3.rules if x.rule_id == "PO-INFER").evidence_json["candidates"]
    assert [c["po_number"] for c in candidates] == ["PO-2026-0104", "PO-2026-0105"]  # chairs PO loses

    # Next actions list exactly what is missing: the invoice number, and the PO to confirm.
    actions = ec3.explanation_json["next_actions"]
    assert actions == [
        "Ask the vendor for the invoice number (not readable on the invoice)",
        "Confirm with the requester that this invoice belongs to PO-2026-0104 (the invoice has no PO reference)",
    ]


def test_ec3_scan_has_no_text_layer(session: Session, real: Settings) -> None:
    ec3 = run(session, real, "EC-3")
    ingest = next(e for e in ec3.events if e.stage == "ingest" and e.status != "RUNNING")
    assert ingest.payload_json["is_scanned"] is True and ingest.payload_json["text_chars"] == 0


# -- EC-4: bank details changed ----------------------------------------------------------------


def test_ec4_bank_change_is_fraud_risk_with_phone_on_file(session: Session, real: Settings) -> None:
    ec4 = run(session, real, "EC-4")
    assert (ec4.decision, ec4.flags) == ("NEEDS_REVIEW", ["FRAUD_RISK"])
    r = rules_of(ec4)
    assert r["VEN-STATUS"][0] == "PASS" and r["PO-EXPLICIT"][0] == "PASS"  # approved vendor, valid PO
    assert r["VEN-BANK"][0] == "FAIL"
    assert ec4.explanation_json["next_actions"] == [
        "Verify the bank change by calling Brightline IT Services Pvt Ltd on the number on file (+91 40 6712 5500), "
        "not any number on the invoice. Do not pay until confirmed."
    ]
    # The new account never appears unmasked in what the reviewer sees.
    assert "045661900002345" not in ec4.explanation_json["verdict"]


def test_ec4_variant_reviewer_approval_consumes_po(session: Session, real: Settings) -> None:
    ec4 = run(session, real, "EC-4")
    assert "PO-2026-0106" not in repo.consumed_by_po(session)
    ec4.reviewer_action, ec4.reviewer_note = "APPROVE", "Called number on file, change confirmed"
    session.commit()
    assert repo.consumed_by_po(session)["PO-2026-0106"] == Decimal("118000.00")


# -- Full section 7 table, fresh DB, demo order ------------------------------------------------

SECTION_7 = {
    "HP-1": ("APPROVED", set()),
    "HP-2": ("APPROVED", set()),
    "EC-1-A": ("APPROVED", set()),
    "EC-1-B": ("APPROVED", set()),
    "EC-1-C": ("NEEDS_REVIEW", {"OVER_PO"}),
    "EC-2": ("REJECTED", {"DUPLICATE"}),
    "EC-3": ("NEEDS_REVIEW", {"LOW_CONFIDENCE", "PO_INFERRED"}),
    "EC-4": ("NEEDS_REVIEW", {"FRAUD_RISK"}),
}


def test_section_7_reproduces_exactly_in_demo_order(session: Session, real: Settings) -> None:
    got = {}
    for name in DEMO_ORDER:
        r = run(session, real, name)
        got[name] = (r.decision, set(r.flags))
        if name == "HP-2":
            assert "Within tolerance" in " ".join(r.explanation_json["why"])
    assert got == SECTION_7


# -- HP-3: invoice for a PO created in the app (A66, A67) -----------------------------------------


def test_hp3_needs_the_po_created_in_the_app(session: Session, real: Settings) -> None:
    from datetime import date

    from app.api_schemas import POCreate
    from app.purchase_orders import create_purchase_order

    from app.pipeline.stages.ingest import sha256
    from app.llm.gemini import fixture_path

    assert fixture_path(sha256((INVOICES / "HP-3.pdf").read_bytes()), real).exists()
    before = run(session, real, "HP-3")
    assert before.decision == "NEEDS_REVIEW" and rules_of(before)["PO-EXPLICIT"][0] == "FAIL"

    body = POCreate(vendor_id="V002", issue_date=date(2026, 11, 7), total_amount="114460.00", lines=[
        {"description": "Bubble wrap roll 1 m x 100 m", "hsn_sac": "3923", "qty": "50", "unit": "Rolls",
         "unit_price": "1200"},
        {"description": "BOPP packing tape 48 mm (box of 72)", "hsn_sac": "3919", "qty": "20", "unit": "Boxes",
         "unit_price": "1850"},
    ])
    assert create_purchase_order(session, body, date(2026, 11, 12)) == "PO-2026-0108"
    # A second, fresh HP-3 run would be a duplicate of the first, so start from a clean runs table.
    from app.seed import wipe_runs
    wipe_runs(session)
    after = run(session, real, "HP-3")
    assert (after.decision, after.flags, after.matched_po) == ("APPROVED", [], "PO-2026-0108")
    assert repo.consumed_by_po(session)["PO-2026-0108"] == Decimal("114460.00")
