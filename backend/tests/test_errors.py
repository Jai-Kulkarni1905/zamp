"""Failure paths: the pipeline must end every run as DONE or ERROR, never crash or hang in RUNNING."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.pipeline import runner
from app.pipeline.events import EventBus
from app.pipeline.runner import create_run, process_run
from tests.conftest import INVOICES


def _start(session: Session, settings: Settings):  # type: ignore[no-untyped-def]
    pdf = INVOICES / "HP-1.pdf"
    return create_run(session, pdf.name, pdf.read_bytes(), settings)


def test_network_error_during_extract_ends_in_error(session: Session, settings: Settings,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(runner, "extract_invoice", boom)
    run = process_run(session, _start(session, settings).id, bus=EventBus(), settings=settings)
    assert run.status == "ERROR" and "network unreachable" in (run.error or "")


def test_failure_outside_a_stage_ends_in_error(session: Session, settings: Settings,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from app.llm.gemini import fixture_path
    from app.pipeline.stages.ingest import sha256
    from tests.factories import make_extraction

    data = (INVOICES / "HP-1.pdf").read_bytes()
    path = fixture_path(sha256(data), settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": "hand-built", "extraction": make_extraction().model_dump(mode="json")}))

    def broken_finish(self: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(runner._Pipeline, "finish", broken_finish)
    run = process_run(session, _start(session, settings).id, bus=EventBus(), settings=settings)
    assert run.status == "ERROR" and "disk full" in (run.error or "")


class _FakeModels:
    def __init__(self, exc: Exception) -> None:
        self.exc, self.calls = exc, 0

    def generate_content(self, **_k: object) -> None:
        self.calls += 1
        raise self.exc


def _fake_client(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> _FakeModels:
    from google import genai

    models = _FakeModels(exc)

    class FakeClient:
        def __init__(self, **_k: object) -> None:
            self.models = models

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr("app.llm.gemini.time.sleep", lambda _s: None)
    return models


def _live(settings: Settings) -> Settings:
    import dataclasses

    return dataclasses.replace(settings, llm_mode="live", gemini_api_key="test-key", gemini_model="test-model")


def test_gemini_network_error_retries_then_fails_cleanly(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm.gemini import LLMError, extract_invoice

    models = _fake_client(monkeypatch, ConnectionError("no route"))
    with pytest.raises(LLMError) as info:
        extract_invoice(b"%PDF", "f" * 64, settings=_live(settings))
    assert info.value.kind == "failed" and "no route" in info.value.message and models.calls == 4


def test_gemini_rate_limit_is_reported_as_such(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from google.genai import errors

    from app.llm.gemini import LLMError, extract_invoice

    models = _fake_client(monkeypatch, errors.ClientError(429, {"error": {"message": "quota"}}))
    with pytest.raises(LLMError) as info:
        extract_invoice(b"%PDF", "e" * 64, settings=_live(settings))
    assert info.value.kind == "rate_limited" and models.calls == 4


def test_gemini_bad_request_is_not_retried(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from google.genai import errors

    from app.llm.gemini import LLMError, extract_invoice

    models = _fake_client(monkeypatch, errors.ClientError(400, {"error": {"message": "bad model"}}))
    with pytest.raises(LLMError) as info:
        extract_invoice(b"%PDF", "d" * 64, settings=_live(settings))
    assert info.value.kind == "failed" and models.calls == 1


def test_fixture_mode_never_builds_a_client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm.gemini import LLMError, extract_invoice

    models = _fake_client(monkeypatch, AssertionError("must not be called"))
    with pytest.raises(LLMError) as info:
        extract_invoice(b"%PDF", "c" * 64, settings=settings)
    assert info.value.kind == "no_fixture" and models.calls == 0


@pytest.mark.parametrize(("raw", "expected"), [(0.95, 0.95), (95, 0.95), (1.05, 1.0), (250, 1.0), (-0.1, 0.0)])
def test_confidence_is_clamped_to_0_1(raw: float, expected: float) -> None:
    from app.schemas import TextField

    assert TextField(value="x", confidence=raw, source_text=None).confidence == pytest.approx(expected)


def test_extraction_schema_sent_to_gemini_has_no_helper_class() -> None:
    from app.schemas import Extraction

    defs = Extraction.model_json_schema()["$defs"]
    assert "_Confident" not in defs and set(defs) == {"TextField", "BoolField", "ExtractedLine", "ExtractedTax"}
