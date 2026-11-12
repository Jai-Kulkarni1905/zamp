"""Stage 5: match the vendor (GSTIN, else fuzzy name), check status and bank details (A16 to A19)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from app.config import T
from app.money import is_valid_gstin, mask_account
from app.pipeline.stages._rules import rule, skipped
from app.schemas import Flag, NormalizedInvoice, Outcome, RuleResult, Severity, Stage, StageResult, VendorRec

S = Stage.VENDOR
_SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "the", "m/s", "ms"}


@dataclass
class VendorMatch:
    vendor: VendorRec
    method: Literal["GSTIN", "NAME"]
    score: float


def normalize_name(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)


def name_score(name: str, vendor: VendorRec) -> float:
    target = normalize_name(name)
    if not target:
        return 0.0
    return max(fuzz.token_sort_ratio(target, normalize_name(n)) for n in [vendor.legal_name, *vendor.aliases])


def find_vendor(inv: NormalizedInvoice, vendors: list[VendorRec]) -> tuple[VendorMatch | None, list[dict[str, object]]]:
    if inv.vendor_gstin:
        for v in vendors:
            if v.gstin == inv.vendor_gstin:
                return VendorMatch(v, "GSTIN", 100.0), [{"vendor_id": v.vendor_id, "name": v.legal_name, "score": 100.0}]
    if not inv.vendor_name:
        return None, []
    scored = sorted(((name_score(inv.vendor_name, v), v) for v in vendors), key=lambda x: -x[0])
    candidates = [{"vendor_id": v.vendor_id, "name": v.legal_name, "score": round(s, 1)} for s, v in scored[:3]]
    if scored and scored[0][0] >= T.VENDOR_FUZZY_MIN:
        return VendorMatch(scored[0][1], "NAME", scored[0][0]), candidates
    return None, candidates


def vendor_key(inv: NormalizedInvoice, match: VendorMatch | None) -> str | None:
    """Identity used for duplicate checks (A26)."""
    if match:
        return f"V:{match.vendor.vendor_id}"
    if is_valid_gstin(inv.vendor_gstin):
        return f"G:{inv.vendor_gstin}"
    if inv.vendor_name:
        return f"N:{normalize_name(inv.vendor_name)}"
    return None


def _digits(value: str | None) -> str | None:
    return re.sub(r"\D", "", value) if value else None


def check_bank(inv: NormalizedInvoice, v: VendorRec) -> list[RuleResult]:
    if not inv.bank_account and not inv.ifsc:
        return [
            skipped(S, "VEN-BANK", "No bank details on the invoice to compare"),
            rule(S, "VEN-BANK-MISSING", Outcome.WARN, Severity.INFO,
                 "Invoice shows no bank details; payment goes to the account on file"),
        ]
    acct_ok = inv.bank_account is None or _digits(inv.bank_account) == _digits(v.bank_account)
    ifsc_ok = inv.ifsc is None or inv.ifsc == v.ifsc
    evidence = {
        "invoice": {"account": mask_account(inv.bank_account), "ifsc": inv.ifsc},
        "master": {"account": mask_account(v.bank_account), "ifsc": v.ifsc},
        "account_matches": acct_ok, "ifsc_matches": ifsc_ok, "phone_on_file": v.phone,
    }
    present = rule(S, "VEN-BANK-MISSING", Outcome.PASS, Severity.INFO, "Bank details shown on the invoice")
    if acct_ok and ifsc_ok:
        return [rule(S, "VEN-BANK", Outcome.PASS, Severity.SOFT, "Bank account and IFSC match the vendor master",
                     evidence, review=True, flag=Flag.FRAUD_RISK), present]
    diffs = [n for n, ok in (("account", acct_ok), ("IFSC", ifsc_ok)) if not ok]
    msg = (f"Bank {' and '.join(diffs)} on the invoice differ from the vendor master: "
           f"{mask_account(inv.bank_account)} / {inv.ifsc} on invoice vs "
           f"{mask_account(v.bank_account)} / {v.ifsc} on file")
    return [rule(S, "VEN-BANK", Outcome.FAIL, Severity.SOFT, msg, evidence, review=True, flag=Flag.FRAUD_RISK), present]


def check_vendor(inv: NormalizedInvoice, vendors: list[VendorRec]) -> tuple[StageResult, VendorMatch | None]:
    match, candidates = find_vendor(inv, vendors)
    if match is None:
        rules = [
            rule(S, "VEN-MATCH", Outcome.FAIL, Severity.SOFT,
                 f"Vendor '{inv.vendor_name or 'unknown'}' not found in the vendor master",
                 {"vendor_name": inv.vendor_name, "gstin": inv.vendor_gstin, "candidates": candidates}, review=True),
            skipped(S, "VEN-GSTIN", "No vendor matched"),
            skipped(S, "VEN-STATUS", "No vendor matched"),
            skipped(S, "VEN-BANK", "No vendor matched"),
        ]
        return StageResult(stage=S, message=rules[0].message, payload={"candidates": candidates}, rules=rules), None

    v = match.vendor
    how = "GSTIN" if match.method == "GSTIN" else f"name (score {match.score:.0f})"
    rules: list[RuleResult] = [
        rule(S, "VEN-MATCH", Outcome.PASS, Severity.SOFT, f"Matched {v.legal_name} ({v.vendor_id}) by {how}",
             {"vendor_id": v.vendor_id, "method": match.method, "score": match.score, "candidates": candidates}),
    ]
    if match.method == "GSTIN":
        rules.append(rule(S, "VEN-GSTIN", Outcome.PASS, Severity.SOFT, "GSTIN matches the vendor master"))
    elif is_valid_gstin(inv.vendor_gstin):
        rules.append(rule(S, "VEN-GSTIN", Outcome.WARN, Severity.SOFT,
                          f"Name matches {v.legal_name} but invoice GSTIN {inv.vendor_gstin} differs from {v.gstin} on file",
                          {"invoice_gstin": inv.vendor_gstin, "master_gstin": v.gstin}, review=True))
    else:
        rules.append(skipped(S, "VEN-GSTIN", "No valid GSTIN on the invoice to compare"))

    blocked = v.status != "APPROVED"
    rules.append(rule(S, "VEN-STATUS", Outcome.FAIL if blocked else Outcome.PASS, Severity.HARD,
                      f"Vendor {v.legal_name} is {v.status} in the vendor master" if blocked
                      else f"Vendor status is {v.status}", {"status": v.status}))
    rules += check_bank(inv, v)

    payload = {
        "vendor": {"vendor_id": v.vendor_id, "legal_name": v.legal_name, "status": v.status, "gstin": v.gstin,
                   "method": match.method, "score": match.score, "phone": v.phone},
        "bank": next((r.evidence for r in rules if r.rule_id == "VEN-BANK"), {}),
        "candidates": candidates,
    }
    bad = [r for r in rules if r.outcome in (Outcome.FAIL, Outcome.WARN) and r.severity != Severity.INFO]
    message = rules[0].message if not bad else bad[0].message
    return StageResult(stage=S, message=message, payload=payload, rules=rules), match
