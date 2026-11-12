"""Stage 2: turn an LLM extraction result (or error) into a StageResult. The call itself is in llm/gemini.py."""

from __future__ import annotations

from typing import Any

from app.config import T
from app.llm.gemini import ExtractionResult, LLMError
from app.schemas import REQUIRED_FIELDS, TOP_LEVEL_FIELDS, Extraction, Stage, StageResult, StageStatus


def fields_table(ex: Extraction) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in TOP_LEVEL_FIELDS:
        f = getattr(ex, name)
        rows.append({
            "field": name,
            "value": f.value,
            "confidence": f.confidence,
            "source_text": f.source_text,
            "required": name in REQUIRED_FIELDS,
            "low_confidence": f.confidence < T.LOW_CONFIDENCE,
        })
    return rows


def extract_ok(result: ExtractionResult) -> StageResult:
    ex = result.extraction
    low = [r["field"] for r in fields_table(ex) if r["low_confidence"]]
    source = "cached extraction" if result.source == "fixture" else f"live call to {result.model}"
    message = f"{len(ex.line_items)} line items via {source}" + (f", low confidence: {', '.join(low)}" if low else "")
    payload = {
        "source": result.source,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "fields": fields_table(ex),
        "line_items": [li.model_dump() for li in ex.line_items],
        "taxes": [t.model_dump() for t in ex.taxes],
    }
    # Confidence is judged in Validate (VAL-CONFIDENCE); extraction itself succeeded.
    return StageResult(stage=Stage.EXTRACT, message=message, payload=payload, status_override=StageStatus.PASS)


def extract_failed(err: LLMError) -> StageResult:
    return StageResult(
        stage=Stage.EXTRACT,
        message=err.message,
        payload={"error_kind": err.kind, "retryable": err.kind in ("rate_limited", "failed")},
        status_override=StageStatus.FAIL,
    )
