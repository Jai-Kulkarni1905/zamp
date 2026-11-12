"""The ONLY module that talks to an LLM.

Gemini reads the invoice PDF into the `Extraction` schema. Nothing here decides anything.
Results are cached as fixtures in data/fixtures/<sha256>.json (A9):
- LLM_MODE=fixture: read the fixture, never call Gemini. Missing fixture is an error.
- LLM_MODE=live: use the fixture if present (unless force=True), else call Gemini and save one.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import Extraction

PROMPT = """You are reading a vendor invoice issued to an Indian company. Extract the fields in the
response schema exactly as printed. Rules:
- vendor_name and vendor_gstin are the SELLER who issued the invoice, never the buyer / bill-to party.
- po_reference is the buyer's purchase order number (labels like "PO No", "Buyer's Order No",
  "Purchase Order"). If none is printed, value is null. Never copy the invoice number into it.
- If a field is not printed on the invoice, value is null. Never guess or invent a value.
- Dates: value in YYYY-MM-DD.
- Amounts, quantities, rates: plain numbers without currency symbols or thousands separators,
  e.g. "177000.00". Keep the sign for negative amounts such as a round off.
- currency: ISO code, e.g. "INR" for Rs., Rupees or the rupee sign.
- subtotal is the taxable value before GST. total is the final amount payable.
- taxes: one entry per tax line (CGST, SGST, IGST) with rate in percent and amount.
- tax_inclusive is true only if line prices are stated as including GST.
- line_items: every billed line, with qty, unit_price and amount as printed.
- confidence (0 to 1): 0.95 or more when the text is clearly printed and unambiguous; 0.7 to 0.9
  when partly legible or you relied on layout; below 0.5 when guessing. For a field that is not
  printed, confidence is how sure you are that it is absent.
- source_text: the exact snippet you read the value from, or null.
"""

FixtureSource = Literal["fixture", "live"]
REQUEST_TIMEOUT_MS = 180_000  # one call per invoice; never hang the pipeline forever
RETRY_BASE_DELAY_S = 4.0


class LLMError(Exception):
    def __init__(self, kind: Literal["no_fixture", "not_configured", "rate_limited", "failed"], message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class ExtractionResult:
    extraction: Extraction
    source: FixtureSource
    model: str | None
    latency_ms: int


def fixture_path(file_hash: str, settings: Settings) -> Path:
    return settings.fixtures_dir / f"{file_hash}.json"


def _load_fixture(path: Path) -> tuple[Extraction, str | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Extraction.model_validate(data["extraction"]), data.get("model")


def _save_fixture(path: Path, file_hash: str, filename: str | None, model: str, extraction: Extraction) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "file_hash": file_hash,
        "filename": filename,
        "model": model,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction": extraction.model_dump(mode="json"),
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _call_gemini(pdf_bytes: bytes, settings: Settings, max_attempts: int = 4) -> Extraction:
    from google import genai
    from google.genai import errors, types

    if not settings.gemini_api_key or not settings.gemini_model:
        raise LLMError("not_configured", "GEMINI_API_KEY and GEMINI_MODEL must be set for live extraction")
    client = genai.Client(api_key=settings.gemini_api_key,
                         http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Extraction,
        temperature=0,
    )
    contents = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), PROMPT]
    delay = RETRY_BASE_DELAY_S
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)
            if isinstance(response.parsed, Extraction):
                return response.parsed
            return Extraction.model_validate_json(response.text or "")
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            retryable = code in (429, 500, 502, 503, 504)
            if not retryable or attempt == max_attempts:
                if code == 429:
                    raise LLMError("rate_limited", "LLM rate limited, retry later") from exc
                raise LLMError("failed", f"Gemini error {code}: {exc}") from exc
        except ValidationError as exc:
            if attempt == max_attempts:
                raise LLMError("failed", f"Gemini returned JSON that does not match the schema: {exc}") from exc
        except Exception as exc:  # network errors, timeouts: retry, then fail cleanly
            if attempt == max_attempts:
                raise LLMError("failed", f"Could not reach Gemini: {type(exc).__name__}: {exc}") from exc
        time.sleep(delay)
        delay *= 2
    raise LLMError("failed", "Gemini extraction failed")  # unreachable


def extract_invoice(
    pdf_bytes: bytes,
    file_hash: str,
    *,
    filename: str | None = None,
    force: bool = False,
    mode: Literal["fixture", "live"] | None = None,
    settings: Settings | None = None,
) -> ExtractionResult:
    settings = settings or get_settings()
    mode = mode or settings.llm_mode
    path = fixture_path(file_hash, settings)
    started = time.perf_counter()

    if path.is_file() and not (force and mode == "live"):
        extraction, model = _load_fixture(path)
        return ExtractionResult(extraction, "fixture", model, int((time.perf_counter() - started) * 1000))
    if mode == "fixture":
        raise LLMError("no_fixture", f"No recorded extraction for this file (hash {file_hash[:12]}) "
                                     "and LLM_MODE=fixture. Record it with LLM_MODE=live.")

    extraction = _call_gemini(pdf_bytes, settings)
    assert settings.gemini_model is not None
    _save_fixture(path, file_hash, filename, settings.gemini_model, extraction)
    return ExtractionResult(extraction, "live", settings.gemini_model, int((time.perf_counter() - started) * 1000))
