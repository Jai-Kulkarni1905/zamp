"""HTTP API through FastAPI's TestClient, with the real worker thread and hand-built fixtures (no Gemini)."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.db import make_engine
from tests.conftest import INVOICES
from tests.test_runner import _write_fixtures

DEMO_ORDER = ["HP-1", "HP-2", "EC-1-A", "EC-1-B", "EC-1-C", "EC-2", "EC-3", "EC-4"]


def _client(settings: Settings, tmp_path: Path) -> TestClient:
    _write_fixtures(settings)
    engine = make_engine(f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    return TestClient(create_app(settings, engine))


@pytest.fixture
def client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    with _client(settings, tmp_path) as c:
        yield c


def upload(client: TestClient, name: str, **params: Any) -> str:
    pdf = INVOICES / f"{name}.pdf"
    r = client.post("/api/runs", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}, params=params)
    assert r.status_code == 201, r.text
    return str(r.json()["run_id"])


def wait(client: TestClient) -> None:
    client.app.state.worker.wait_idle()  # type: ignore[attr-defined]


def read_sse(client: TestClient, run_id: str, headers: dict[str, str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    with client.stream("GET", f"/api/runs/{run_id}/events", headers=headers or {}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        kind = ""
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
    return events


# -- upload, detail, file ------------------------------------------------------


def test_upload_and_detail(client: TestClient) -> None:
    run_id = upload(client, "HP-1")
    wait(client)
    d = client.get(f"/api/runs/{run_id}").json()
    assert (d["status"], d["decision"], d["flags"]) == ("DONE", "APPROVED", [])
    assert d["vendor_name"] == "Shakti Industrial Supplies Pvt Ltd"
    assert d["total"] == "177000.00"  # money is a string, never a float
    assert [s["stage"] for s in d["stages"]][0] == "ingest" and len(d["stages"]) == 10
    assert all(s["status"] == "PASS" for s in d["stages"])
    assert d["po"]["consumed"] == "177000.00" and d["po"]["remaining"] == "0.00"
    assert any(r["rule_id"] == "AMT-REMAINING" for r in d["rules"])
    assert d["explanation"]["verdict"].startswith("Approved")
    assert d["created_at"].endswith(("Z", "+00:00"))  # timezone-aware


def test_file_is_served_inline(client: TestClient) -> None:
    run_id = upload(client, "HP-2")
    r = client.get(f"/api/runs/{run_id}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content == (INVOICES / "HP-2.pdf").read_bytes()
    assert r.headers["content-disposition"].startswith("inline")


def test_upload_validation(client: TestClient) -> None:
    r = client.post("/api/runs", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400 and "Not a PDF" in r.text
    big = b"%PDF-1.4\n" + b"0" * (15 * 1024 * 1024)
    assert client.post("/api/runs", files={"file": ("big.pdf", big, "application/pdf")}).status_code == 413
    pdf = (INVOICES / "HP-1.pdf").read_bytes()
    r = client.post("/api/runs", files={"file": ("HP-1.pdf", pdf, "application/pdf")}, params={"force_extract": True})
    assert r.status_code == 400 and "LLM_MODE=live" in r.text


def test_unknown_run_is_404(client: TestClient) -> None:
    for path in ("", "/file", "/events"):
        assert client.get(f"/api/runs/nope{path}").status_code == 404


# -- SSE -------------------------------------------------------------------------


def test_sse_streams_live_stages(settings: Settings, tmp_path: Path) -> None:
    slow = dataclasses.replace(settings, stage_delay_ms=40)  # connect while the run is still going
    with _client(slow, tmp_path) as client:
        run_id = upload(client, "HP-1")
        events = read_sse(client, run_id)
    stages = [e for k, e in events if k == "stage"]
    assert [e["status"] for e in stages] == ["RUNNING", "PASS"] * 10
    assert [e["seq"] for e in stages] == list(range(1, 21))
    kind, end = events[-1]
    assert kind == "end" and end["status"] == "DONE" and end["decision"] == "APPROVED"


def test_sse_replays_finished_run_and_honours_last_event_id(client: TestClient) -> None:
    run_id = upload(client, "EC-4")
    wait(client)
    full = read_sse(client, run_id)
    assert sum(1 for k, _ in full if k == "stage") == 20 and full[-1][1]["decision"] == "NEEDS_REVIEW"
    tail = read_sse(client, run_id, {"Last-Event-ID": "18"})
    assert [e["seq"] for k, e in tail if k == "stage"] == [19, 20] and tail[-1][0] == "end"


def test_sse_for_failed_run_ends_with_error(client: TestClient, settings: Settings) -> None:
    for f in settings.fixtures_dir.glob("*.json"):
        f.unlink()
    run_id = upload(client, "HP-1")
    events = read_sse(client, run_id)
    statuses = [e["status"] for k, e in events if k == "stage" and e["status"] != "RUNNING"]
    assert statuses[:2] == ["PASS", "FAIL"] and set(statuses[2:]) == {"SKIPPED"}
    assert events[-1] == ("end", {"run_id": run_id, "status": "ERROR", "decision": None, "flags": []})


# -- demo order: list, filters, PO balances, stats, review --------------------------


@pytest.fixture
def demo(client: TestClient) -> dict[str, str]:
    ids = {name: upload(client, name) for name in DEMO_ORDER}
    wait(client)
    return ids


def test_demo_decisions_via_api(client: TestClient, demo: dict[str, str]) -> None:
    got = {n: (client.get(f"/api/runs/{i}").json()["decision"]) for n, i in demo.items()}
    assert got == {"HP-1": "APPROVED", "HP-2": "APPROVED", "EC-1-A": "APPROVED", "EC-1-B": "APPROVED",
                   "EC-1-C": "NEEDS_REVIEW", "EC-2": "REJECTED", "EC-3": "NEEDS_REVIEW", "EC-4": "NEEDS_REVIEW"}


def test_list_and_filters(client: TestClient, demo: dict[str, str]) -> None:
    body = client.get("/api/runs").json()
    assert body["total"] == 8 and body["items"][0]["filename"] == "EC-4.pdf"  # newest first
    assert client.get("/api/runs", params={"decision": "APPROVED"}).json()["total"] == 4
    assert client.get("/api/runs", params={"review_queue": True}).json()["total"] == 3
    assert [i["filename"] for i in client.get("/api/runs", params={"flag": "FRAUD_RISK"}).json()["items"]] == ["EC-4.pdf"]
    assert client.get("/api/runs", params={"vendor_id": "V003"}).json()["total"] == 3
    assert client.get("/api/runs", params={"q": "nilgiri"}).json()["total"] == 1
    assert client.get("/api/runs", params={"q": "INV/2026"}).json()["total"] == 2  # EC-2 and BITS/INV/2026/1187
    assert client.get("/api/runs", params={"q": "INV/2026/0142"}).json()["total"] == 1
    page = client.get("/api/runs", params={"limit": 3, "offset": 6}).json()
    assert page["total"] == 8 and len(page["items"]) == 2
    assert client.get("/api/runs", params={"decision": "MAYBE"}).status_code == 422


def test_po_balances_show_split_po(client: TestClient, demo: dict[str, str]) -> None:
    pos = {p["po_number"]: p for p in client.get("/api/pos").json()}
    split = pos["PO-2026-0103"]
    assert (split["total"], split["consumed"], split["remaining"]) == ("300000.00", "240000.00", "60000.00")
    assert [(i["filename"], i["counts_against_po"]) for i in split["invoices"]] == [
        ("EC-1-A.pdf", True), ("EC-1-B.pdf", True), ("EC-1-C.pdf", False)]
    assert pos["PO-2026-0101"]["remaining"] == "0.00"
    assert pos["PO-2026-0102"]["remaining"] == "-3010.00"  # HP-2 approved within tolerance
    assert pos["PO-2026-0104"]["consumed"] == "0.00"  # EC-3 inferred but waiting for review


def test_stats(client: TestClient, demo: dict[str, str]) -> None:
    s = client.get("/api/stats").json()
    assert (s["runs_total"], s["runs_done"], s["runs_error"], s["runs_in_progress"]) == (8, 8, 0, 0)
    assert s["decisions"] == {"APPROVED": 4, "NEEDS_REVIEW": 3, "REJECTED": 1}
    assert s["approval_rate"] == 0.5 and s["review_queue"] == 3
    expected_total = Decimal("177000") * 2 + Decimal("203610") + 240000 + 90000 + 106200 + 118000
    assert Decimal(s["value_processed"]) == expected_total
    assert Decimal(s["value_approved"]) == Decimal("177000") + 203610 + 240000
    assert s["flags"]["DUPLICATE"] == 1 and s["flags"]["OVER_PO"] == 2


def test_review_override(client: TestClient, demo: dict[str, str]) -> None:
    ec4 = demo["EC-4"]
    assert client.post(f"/api/runs/{ec4}/review", json={"action": "APPROVE", "note": "  "}).status_code == 422
    assert client.post(f"/api/runs/{ec4}/review", json={"action": "MAYBE", "note": "x"}).status_code == 422
    r = client.post(f"/api/runs/{ec4}/review",
                    json={"action": "APPROVE", "note": "Called +91 40 6712 5500, bank change confirmed"})
    body = r.json()
    assert r.status_code == 200 and body["decision"] == "NEEDS_REVIEW" and body["effective_decision"] == "APPROVED"
    assert body["reviewer_note"].startswith("Called") and body["reviewed_at"]
    assert body["po"]["consumed"] == "118000.00"
    again = client.post(f"/api/runs/{ec4}/review", json={"action": "REJECT", "note": "changed my mind"})
    assert again.status_code == 409
    s = client.get("/api/stats").json()
    assert s["review_queue"] == 2 and s["effective_decisions"]["APPROVED"] == 5


def test_review_rejected_override_frees_nothing_and_unknown_is_404(client: TestClient, demo: dict[str, str]) -> None:
    r = client.post(f"/api/runs/{demo['EC-1-C']}/review", json={"action": "REJECT", "note": "Over PO, sent back"})
    assert r.json()["po"]["consumed"] == "240000.00"
    assert client.post("/api/runs/nope/review", json={"action": "REJECT", "note": "x"}).status_code == 404


# -- vendors, admin -------------------------------------------------------------


def test_vendors_masked(client: TestClient) -> None:
    vendors = client.get("/api/vendors").json()
    assert len(vendors) == 6 and vendors[0]["bank_account_masked"] == "XXXX5678"
    assert "bank_account" not in vendors[0]
    assert [v["vendor_id"] for v in vendors if v["status"] == "BLOCKED"] == ["V006"]


def test_admin_reset(client: TestClient, demo: dict[str, str]) -> None:
    r = client.post("/api/admin/reset")
    assert r.status_code == 200 and r.json()["runs_removed"] == 8
    assert client.get("/api/runs").json()["total"] == 0
    assert client.get("/api/pos").json()[2]["consumed"] == "0.00"


def test_admin_reset_requires_token_when_configured(settings: Settings, tmp_path: Path) -> None:
    with _client(dataclasses.replace(settings, admin_token="s3cret"), tmp_path) as client:
        assert client.post("/api/admin/reset").status_code == 401
        assert client.post("/api/admin/reset", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert client.post("/api/admin/reset", headers={"X-Admin-Token": "s3cret"}).status_code == 200


def test_health_and_cors(client: TestClient) -> None:
    assert client.get("/api/health").json()["llm_mode"] == "fixture"
    r = client.options("/api/runs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
