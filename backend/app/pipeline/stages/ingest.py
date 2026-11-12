"""Stage 1: hash, page count, text layer detection (A8)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import pdfplumber

from app.config import T
from app.pipeline.stages._rules import rule
from app.schemas import Outcome, Severity, Stage, StageResult


@dataclass
class IngestData:
    file_hash: str
    page_count: int
    is_scanned: bool
    pdf_text: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_pdf(pdf_bytes: bytes) -> tuple[int, str]:
    """Page count and the concatenated text layer. Raises if the bytes are not a readable PDF."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texts = [page.extract_text() or "" for page in pdf.pages]
        return len(pdf.pages), "\n".join(texts)


def ingest(pdf_bytes: bytes, filename: str, seen_before: bool) -> tuple[StageResult, IngestData]:
    file_hash = sha256(pdf_bytes)
    page_count, text = read_pdf(pdf_bytes)
    chars = len("".join(text.split()))
    is_scanned = page_count == 0 or chars / max(page_count, 1) < T.SCANNED_CHARS_PER_PAGE
    data = IngestData(file_hash=file_hash, page_count=page_count, is_scanned=is_scanned, pdf_text=text)

    layer = rule(
        Stage.INGEST, "ING-SCANNED", Outcome.PASS, Severity.INFO,
        "No text layer: treated as a scanned image, grounding check will be skipped" if is_scanned
        else f"Text layer found ({chars} characters)",
        {"chars": chars, "pages": page_count, "is_scanned": is_scanned},
    )
    message = f"{page_count} page{'s' if page_count != 1 else ''}, " + (
        "scanned image" if is_scanned else "text PDF") + (", seen before" if seen_before else "")
    payload = {
        "filename": filename, "size_bytes": len(pdf_bytes), "file_hash": file_hash, "pages": page_count,
        "is_scanned": is_scanned, "text_chars": chars, "seen_before": seen_before,
    }
    return StageResult(stage=Stage.INGEST, message=message, payload=payload, rules=[layer]), data
