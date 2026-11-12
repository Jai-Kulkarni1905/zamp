"""Stage 10: template-based explanation built only from rule results (A31). No LLM."""

from __future__ import annotations

from datetime import date
from typing import Callable

from app.money import inr, mask_account
from app.pipeline.stages._rules import FIELD_LABELS
from app.pipeline.stages.po_match import POMatch
from app.pipeline.stages.vendor import VendorMatch
from app.schemas import (
    Decision,
    DecisionResult,
    Explanation,
    NormalizedInvoice,
    Outcome,
    RuleResult,
    Severity,
    Stage,
    StageResult,
)

Ctx = tuple[NormalizedInvoice, VendorMatch | None, POMatch | None]


def _missing_actions(r: RuleResult, _: Ctx) -> list[str]:
    out = []
    for f in r.evidence.get("missing", []):
        label = FIELD_LABELS.get(f, f)
        out.append(f"Ask the vendor for the {label} (not readable on the invoice)")
    return out


def _bank_action(r: RuleResult, ctx: Ctx) -> list[str]:
    _, vm, _ = ctx
    name = vm.vendor.legal_name if vm else "the vendor"
    phone = r.evidence.get("phone_on_file", "on file")
    return [f"Verify the bank change by calling {name} on the number on file ({phone}), not any number on the "
            "invoice. Do not pay until confirmed."]


def _po_infer_action(r: RuleResult, ctx: Ctx) -> list[str]:
    _, _, pm = ctx
    if r.outcome == Outcome.WARN and pm:
        return [f"Confirm with the requester that this invoice belongs to {pm.po.po_number} "
                "(the invoice has no PO reference)"]
    return ["Ask the vendor or requester which PO this invoice is for"]


def _amount_action(r: RuleResult, ctx: Ctx) -> list[str]:
    po = r.evidence.get("po_number", "the PO")
    return [f"Ask procurement to amend {po} or ask the vendor for a revised invoice"]


def _dup_action(r: RuleResult, _: Ctx) -> list[str]:
    return [f"Do not pay. Compare with the original run ({r.evidence.get('original_filename')})"]


NEXT_ACTIONS: dict[str, Callable[[RuleResult, Ctx], list[str]]] = {
    "VAL-REQUIRED": _missing_actions,
    "VAL-CONFIDENCE": lambda r, _: [
        f"Check the {', '.join(FIELD_LABELS.get(f, f) for f in r.evidence.get('low_fields', {}))} against the PDF "
        "(low extraction confidence)"],
    "VAL-GROUNDING": lambda r, _: ["Compare the extracted values with the PDF; they could not be found in its text"],
    "VAL-ARITH-LINES": lambda r, _: ["Ask the vendor for a corrected invoice; the amounts do not add up"],
    "VAL-ARITH-TOTAL": lambda r, _: ["Ask the vendor for a corrected invoice; the amounts do not add up"],
    "VAL-DATE-FUTURE": lambda r, _: ["Confirm the invoice date with the vendor; it is in the future"],
    "VAL-DATE-STALE": lambda r, _: [
        f"Confirm why a {r.evidence.get('age_days')} day old invoice is being submitted now"],
    "VAL-GSTIN-FORMAT": lambda r, _: ["Ask the vendor to confirm their GSTIN"],
    "VAL-CURRENCY": lambda r, _: ["Confirm the currency with procurement; all POs are in INR"],
    "VEN-MATCH": lambda r, _: ["Check whether this is a new vendor that must be onboarded before payment"],
    "VEN-GSTIN": lambda r, _: ["Confirm the GSTIN with the vendor using the contact details on file"],
    "VEN-STATUS": lambda r, _: ["Do not pay. The vendor is blocked in the vendor master"],
    "VEN-BANK": _bank_action,
    "PO-EXPLICIT": lambda r, _: ["Ask the requester for the correct, open PO for this vendor"],
    "PO-INFER": _po_infer_action,
    "AMT-REMAINING": _amount_action,
    "DUP-HASH": _dup_action,
    "DUP-NUMBER": _dup_action,
    "DUP-FUZZY": _dup_action,
}

_SEVERITY_RANK = {Severity.HARD: 0, Severity.SOFT: 1, Severity.INFO: 2}


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else "the due date"


def explain(decision: DecisionResult, rules: list[RuleResult], inv: NormalizedInvoice,
            vendor: VendorMatch | None, po: POMatch | None) -> tuple[StageResult, Explanation]:
    ctx: Ctx = (inv, vendor, po)
    reasons = [r for r in rules if r.outcome == Outcome.FAIL or (r.outcome == Outcome.WARN and r.review_reason)]
    if decision.decision == Decision.REJECTED:
        reasons = [r for r in reasons if r.severity == Severity.HARD] + \
                  [r for r in reasons if r.severity != Severity.HARD]
    else:
        reasons.sort(key=lambda r: _SEVERITY_RANK[r.severity])  # stable: keeps pipeline order within a severity
    notes = [r for r in rules if r.outcome == Outcome.WARN and not r.review_reason]

    if decision.decision == Decision.APPROVED:
        why = [r.message for r in rules if r.rule_id in ("VEN-MATCH", "PO-EXPLICIT", "AMT-REMAINING", "DUP-NUMBER")
               and r.outcome == Outcome.PASS]
        why.append("All data quality checks passed")
        assert po is not None and inv.total is not None
        after = po.po.remaining - inv.total
        balance = (f"{inr(after)} left on the PO" if after >= 0
                   else f"PO over by {inr(-after)}, within tolerance")
        verdict = f"Approved: {inr(inv.total)} against {po.po.po_number}, {balance}"
        account = mask_account(vendor.vendor.bank_account) if vendor else None
        actions = [f"Schedule payment of {inr(inv.total)} by {_fmt_date(inv.due_date)} to the account on file ({account})"]
    else:
        why = [r.message for r in reasons]
        head = reasons[0].message if reasons else decision.decision.value
        more = f" (+{len(reasons) - 1} more)" if len(reasons) > 1 else ""
        verdict = ("Rejected: " if decision.decision == Decision.REJECTED else "Needs review: ") + head + more
        # A rejected invoice is not paid, so only the HARD reasons get actions (A42).
        acting = [r for r in reasons if r.severity == Severity.HARD] \
            if decision.decision == Decision.REJECTED else reasons
        actions = []
        for r in acting:
            for a in NEXT_ACTIONS.get(r.rule_id, lambda _r, _c: [])(r, ctx):
                if a not in actions:
                    actions.append(a)

    why += [f"Note: {r.message}" for r in notes]
    exp = Explanation(verdict=verdict, why=why, next_actions=actions)
    stage = StageResult(stage=Stage.EXPLAIN, message=verdict, payload=exp.model_dump(mode="json"))
    return stage, exp
