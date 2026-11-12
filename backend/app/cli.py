"""Command line entry point.

    python -m app.cli run <pdf> [--force-extract] [--json]
    python -m app.cli reset                 wipe runs, reseed vendors and POs
    python -m app.cli demo                  RESET, then all test invoices in demo order vs PLAN.md section 7
    python -m app.cli record-fixtures [--only HP-1 ...]   LIVE Gemini calls, one per uncached PDF
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.config import ROOT, get_settings
from app.db import session_factory
from app.models import RuleResultRow, Run, Vendor
from app.pipeline.events import EventBus
from app.pipeline.runner import create_run, process_run
from app.schemas import StageEventOut, StageStatus
from app.seed import seed_master_data, wipe_runs

ICON = {StageStatus.PASS: "PASS", StageStatus.WARN: "WARN", StageStatus.FAIL: "FAIL", StageStatus.SKIPPED: "SKIP"}


def _resolve(path: str) -> Path:
    p = Path(path)
    if p.exists():
        return p
    alt = ROOT / path
    if alt.exists():
        return alt
    sys.exit(f"File not found: {path}")


def _print_event(e: StageEventOut) -> None:
    if e.status == StageStatus.RUNNING:
        return
    ms = e.payload.get("duration_ms", "")
    print(f"  [{ICON[e.status]}] {e.stage.value:<11} {str(ms) + 'ms' if ms != '' else '':>7}  {e.message}")


def cmd_run(args: argparse.Namespace) -> int:
    if args.force_extract and get_settings().llm_mode != "live":
        sys.exit("--force-extract needs LLM_MODE=live (it makes a real Gemini call). Set it in .env or the shell.")
    Session = session_factory()
    with Session() as session:
        if not session.scalar(select(func.count()).select_from(Vendor)):
            seed_master_data(session, get_settings().seed_dir)
        path = _resolve(args.pdf)
        run = create_run(session, path.name, path.read_bytes())
        bus = EventBus()
        if not args.json:
            print(f"Run {run.id}  {path.name}")
            bus.subscribe(_print_event, run.id)
        run = process_run(session, run.id, bus=bus, force_extract=args.force_extract)
        rules = session.scalars(select(RuleResultRow).where(RuleResultRow.run_id == run.id)).all()
        result = {
            "run_id": run.id,
            "file": run.filename,
            "status": run.status,
            "decision": run.decision,
            "flags": run.flags,
            "vendor_id": run.vendor_id,
            "invoice_number": run.invoice_number,
            "total": str(run.total) if run.total is not None else None,
            "matched_po": run.matched_po,
            "po_match_type": run.po_match_type,
            "explanation": run.explanation_json,
            "error": run.error,
            "triggered_rules": [
                {"rule_id": r.rule_id, "outcome": r.outcome, "severity": r.severity, "message": r.message}
                for r in rules if r.outcome in ("WARN", "FAIL")
            ],
            "duration_ms": run.duration_ms,
        }
        if not args.json:
            print()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if run.status == "DONE" else 1


def cmd_reset(_: argparse.Namespace) -> int:
    Session = session_factory()
    with Session() as session:
        removed = wipe_runs(session)
        counts = seed_master_data(session, get_settings().seed_dir)
    print(f"Removed {removed} run(s). Seeded {counts}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    from app.llm.gemini import LLMError, extract_invoice, fixture_path
    from app.pipeline.stages.ingest import sha256

    settings = get_settings()
    pdfs = sorted((ROOT / "data" / "invoices").glob("*.pdf"))
    if args.only:
        pdfs = [p for p in pdfs if p.stem in set(args.only)]
    todo = [p for p in pdfs if not fixture_path(sha256(p.read_bytes()), settings).exists()]
    print(f"{len(pdfs)} PDF(s), {len(pdfs) - len(todo)} already cached, {len(todo)} live Gemini call(s) "
          f"with model {settings.gemini_model}")
    failures = 0
    for p in todo:
        data = p.read_bytes()
        try:
            res = extract_invoice(data, sha256(data), filename=p.name, mode="live", settings=settings)
            ex = res.extraction
            print(f"  {p.name:<11} {res.latency_ms:>6}ms  vendor={ex.vendor_name.value!r} "
                  f"no={ex.invoice_number.value!r} total={ex.total.value!r} lines={len(ex.line_items)}")
        except LLMError as err:
            failures += 1
            print(f"  {p.name:<11} FAILED ({err.kind}): {err.message}")
    return 1 if failures else 0


def cmd_demo(_: argparse.Namespace) -> int:
    """Fresh reset, then every test invoice in demo order (manifest run_order), vs PLAN.md section 7."""
    manifest = json.loads((ROOT / "data" / "invoices" / "manifest.json").read_text(encoding="utf-8"))
    invoices = sorted(manifest["invoices"], key=lambda i: i["run_order"])
    Session = session_factory()
    bus = EventBus()
    failures = 0
    with Session() as session:
        wipe_runs(session)
        seed_master_data(session, get_settings().seed_dir)
        print(f"Fresh reset. Running {len(invoices)} invoices in demo order.\n")
        print(f"  {'#':<2} {'ID':<7} {'Expected':<34} {'Actual':<34} Result")
        for inv in invoices:
            path = ROOT / "data" / "invoices" / inv["file"]
            run = process_run(session, create_run(session, path.name, path.read_bytes()).id, bus=bus)
            want = (inv["expected"]["decision"], set(inv["expected"]["flags"]))
            got = (run.decision, set(run.flags or []))
            ok = run.status == "DONE" and got == want
            failures += not ok
            show = lambda d, f: f"{d} {','.join(sorted(f))}".strip()  # noqa: E731
            print(f"  {inv['run_order']:<2} {inv['id']:<7} {show(*want):<34} {show(str(got[0]), got[1]):<34} "
                  f"{'PASS' if ok else 'FAIL'}")
            if inv["id"] in ("EC-1-C", "EC-3", "EC-4") or not ok:
                print(f"{'':14}{run.explanation_json['verdict'] if run.explanation_json else run.error}")
    print(f"\n{len(invoices) - failures}/{len(invoices)} match PLAN.md section 7")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # ₹ on Windows consoles
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process one invoice PDF")
    r.add_argument("pdf")
    r.add_argument("--force-extract", action="store_true", help="bypass the fixture cache (needs LLM_MODE=live)")
    r.add_argument("--json", action="store_true", help="print only the decision JSON")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("reset", help="wipe runs and reseed master data").set_defaults(fn=cmd_reset)
    sub.add_parser("demo", help="RESETS the DB, then runs all test invoices in demo order and checks "
                                "them against PLAN.md section 7").set_defaults(fn=cmd_demo)
    rec = sub.add_parser("record-fixtures", help="LIVE: record Gemini extractions for data/invoices/*.pdf")
    rec.add_argument("--only", nargs="*", help="scenario ids, e.g. HP-1 EC-3")
    rec.set_defaults(fn=cmd_record)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
