"""Demo rehearsal against a running deployment (PLAN.md Layer 7): reset, then upload every test invoice in
demo order over HTTP, follow each live SSE stream to its end, and compare with PLAN.md section 7.
Repeats for --rounds (default 2). Exits non-zero on any error or mismatch.

Usage:
    python scripts/rehearse.py --base-url http://127.0.0.1:8000
    python scripts/rehearse.py --base-url https://your-app.onrender.com --admin-token <token>
The admin token can also come from the ADMIN_TOKEN environment variable. It is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
INVOICES = ROOT / "data" / "invoices"

# Balances after all 8 invoices in demo order (EC-1 split PO, HP-2 within tolerance).
EXPECTED_PO = {
    "PO-2026-0101": ("177000.00", "0.00"),
    "PO-2026-0102": ("203610.00", "-3010.00"),
    "PO-2026-0103": ("240000.00", "60000.00"),
}
EXPECTED_STATS = {"runs_done": 8, "runs_error": 0, "review_queue": 3, "value_processed": "1111810.00"}


def wait_until_up(client: httpx.Client, timeout_s: float = 180) -> float:
    """Free hosts sleep when idle; the first request can take a minute while the service wakes."""
    start = time.monotonic()
    while True:
        try:
            if client.get("/api/health", timeout=30).status_code == 200:
                return time.monotonic() - start
        except httpx.HTTPError:
            pass
        if time.monotonic() - start > timeout_s:
            sys.exit(f"Service did not come up within {timeout_s:.0f}s")
        time.sleep(3)


def follow(client: httpx.Client, run_id: str) -> tuple[dict[str, object], int]:
    """Read the SSE stream until the end event. Returns (end payload, number of stage events)."""
    stages = 0
    kind = ""
    with client.stream("GET", f"/api/runs/{run_id}/events", timeout=httpx.Timeout(10, read=120)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                if kind == "end":
                    return json.loads(line[6:]), stages
                stages += 1
    raise RuntimeError("stream closed without an end event")


def one_round(client: httpx.Client, invoices: list[dict[str, object]], token: str | None, n: int) -> int:
    headers = {"X-Admin-Token": token} if token else {}
    reset = client.post("/api/admin/reset", headers=headers, timeout=60)
    if reset.status_code != 200:
        print(f"  reset failed: HTTP {reset.status_code} {reset.text[:120]}")
        return 1
    print(f"\nRound {n}: reset ok ({reset.json()['runs_removed']} runs removed)")
    print(f"  {'#':<2} {'ID':<7} {'Expected':<38} {'Actual':<38} {'Time':>6}  Result")
    problems = 0
    for inv in invoices:
        pdf = INVOICES / str(inv["file"])
        t0 = time.monotonic()
        try:
            created = client.post("/api/runs", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}, timeout=60)
            created.raise_for_status()
            end, events = follow(client, created.json()["run_id"])
        except (httpx.HTTPError, RuntimeError) as exc:
            problems += 1
            print(f"  {inv['run_order']:<2} {inv['id']:<7} ERROR {exc}")
            continue
        exp = inv["expected"]
        want = f"{exp['decision']} {','.join(sorted(exp['flags']))}".strip()
        got = f"{end['decision']} {','.join(sorted(end['flags']))}".strip()
        ok = end["status"] == "DONE" and want == got and events == 20
        problems += not ok
        note = "" if events == 20 else f" ({events} events)"
        print(f"  {inv['run_order']:<2} {inv['id']:<7} {want:<38} {got:<38} {time.monotonic() - t0:>5.1f}s  "
              f"{'PASS' if ok else 'FAIL'}{note}")

    stats = client.get("/api/stats").json()
    for key, want_value in EXPECTED_STATS.items():
        if str(stats[key]) != str(want_value):
            problems += 1
            print(f"  stats.{key}: expected {want_value}, got {stats[key]}")
    pos = {p["po_number"]: (p["consumed"], p["remaining"]) for p in client.get("/api/pos").json()}
    for po, want_bal in EXPECTED_PO.items():
        if pos.get(po) != want_bal:
            problems += 1
            print(f"  {po}: expected consumed/remaining {want_bal}, got {pos.get(po)}")
    print(f"  Dashboard: {stats['runs_done']} runs, review queue {stats['review_queue']}, "
          f"value {stats['value_processed']}, split PO remaining {pos.get('PO-2026-0103', ('?', '?'))[1]}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-token", default=os.environ.get("ADMIN_TOKEN"))
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    manifest = json.loads((INVOICES / "manifest.json").read_text(encoding="utf-8"))
    invoices = sorted(manifest["invoices"], key=lambda i: i["run_order"])
    with httpx.Client(base_url=args.base_url.rstrip("/"), follow_redirects=True) as client:
        waited = wait_until_up(client)
        health = client.get("/api/health").json()
        print(f"{args.base_url} is up (waited {waited:.0f}s), LLM_MODE={health['llm_mode']}")
        total = sum(one_round(client, invoices, args.admin_token, n) for n in range(1, args.rounds + 1))
    print(f"\n{'ZERO ERRORS' if total == 0 else f'{total} PROBLEM(S)'} across {args.rounds} round(s)")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
