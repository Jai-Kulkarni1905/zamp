"""Stage 8: duplicate checks against earlier runs (A25, A26). All HARD."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.config import T
from app.money import inr
from app.pipeline.stages._rules import rule, skipped
from app.schemas import Flag, NormalizedInvoice, Outcome, PriorRun, RuleResult, Severity, Stage, StageResult

S = Stage.DUPLICATES


def _ref(p: PriorRun) -> dict[str, Any]:
    return {"run_id": p.run_id, "filename": p.filename, "invoice_number": p.invoice_number,
            "invoice_date": p.invoice_date, "total": p.total}


def _dup(rule_id: str, message: str, matches: list[PriorRun], **extra: Any) -> RuleResult:
    first = matches[0]
    return rule(S, rule_id, Outcome.FAIL, Severity.HARD, message,
                {"original_run_id": first.run_id, "original_filename": first.filename,
                 "matches": [_ref(p) for p in matches], **extra}, flag=Flag.DUPLICATE)


def check_duplicates(file_hash: str, inv: NormalizedInvoice, vendor_key: str | None,
                     prior: list[PriorRun]) -> StageResult:
    rules: list[RuleResult] = []

    same_file = [p for p in prior if p.file_hash == file_hash]
    rules.append(_dup("DUP-HASH", f"Exact same file was already processed as {same_file[0].filename}", same_file)
                 if same_file else rule(S, "DUP-HASH", Outcome.PASS, Severity.HARD, "File not seen before"))

    if not inv.invoice_number_canonical or not vendor_key:
        rules.append(skipped(S, "DUP-NUMBER", "Invoice number or vendor unknown"))
    else:
        same_no = [p for p in prior if p.vendor_key == vendor_key
                   and p.invoice_number_canonical == inv.invoice_number_canonical]
        rules.append(
            _dup("DUP-NUMBER",
                 f"Same vendor and invoice number as {same_no[0].filename} "
                 f"({inv.invoice_number} vs {same_no[0].invoice_number})", same_no,
                 canonical=inv.invoice_number_canonical)
            if same_no else rule(S, "DUP-NUMBER", Outcome.PASS, Severity.HARD,
                                 f"No earlier invoice {inv.invoice_number} from this vendor"))

    if not (vendor_key and inv.invoice_number_canonical and inv.total is not None and inv.invoice_date):
        rules.append(skipped(S, "DUP-FUZZY", "Needs vendor, invoice number, total and date"))
    else:
        near: list[PriorRun] = []
        sims: dict[str, float] = {}
        for p in prior:
            if (p.vendor_key != vendor_key or p.total is None or p.invoice_date is None
                    or not p.invoice_number_canonical):
                continue
            sim = fuzz.ratio(inv.invoice_number_canonical, p.invoice_number_canonical)
            if (abs(p.total - inv.total) <= T.DUP_TOTAL_TOLERANCE
                    and abs((p.invoice_date - inv.invoice_date).days) <= T.DUP_DATE_WINDOW_DAYS
                    and sim >= T.DUP_NUMBER_SIMILARITY):
                near.append(p)
                sims[p.run_id] = round(sim, 1)
        rules.append(
            _dup("DUP-FUZZY",
                 f"Looks like a re-sent copy of {near[0].filename}: same vendor, total {inr(inv.total)}, "
                 f"date within {T.DUP_DATE_WINDOW_DAYS} days, invoice number {sims[near[0].run_id]:.0f}% similar",
                 near, similarity=sims)
            if near else rule(S, "DUP-FUZZY", Outcome.PASS, Severity.HARD, "No near-identical earlier invoice"))

    hits = [r for r in rules if r.outcome == Outcome.FAIL]
    message = hits[0].message if hits else f"No duplicates among {len(prior)} earlier run(s)"
    originals = {r.evidence["original_run_id"]: r.evidence["original_filename"] for r in hits}
    return StageResult(stage=S, message=message, rules=rules,
                       payload={"compared_against": len(prior),
                                "originals": [{"run_id": k, "filename": v} for k, v in originals.items()]})
