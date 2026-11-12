"""Settings from environment variables, plus the rule thresholds from docs/assumptions.md.

Environment is the only source of runtime config. A `.env` file at the repo root is read at
startup if present; real environment variables always win over it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
# IST is a fixed +05:30 with no DST, so a fixed offset avoids needing the tzdata package on Windows.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments, no interpolation."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


LLMMode = Literal["fixture", "live"]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str | None
    llm_mode: LLMMode
    database_url: str
    as_of_date: date | None
    fixtures_dir: Path
    uploads_dir: Path
    seed_dir: Path
    stage_delay_ms: int = 0
    admin_token: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    def today(self) -> date:
        """Processing date for date rules (A3): AS_OF_DATE if set, else today in IST."""
        return self.as_of_date or datetime.now(IST).date()


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    mode = (_env("LLM_MODE") or "fixture").lower()
    if mode not in ("fixture", "live"):
        raise ValueError(f"LLM_MODE must be 'fixture' or 'live', got {mode!r}")
    as_of = _env("AS_OF_DATE")
    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL"),
        llm_mode=mode,  # type: ignore[arg-type]
        database_url=_env("DATABASE_URL") or f"sqlite:///{(ROOT / 'data' / 'ap.db').as_posix()}",
        as_of_date=date.fromisoformat(as_of) if as_of else None,
        fixtures_dir=ROOT / "data" / "fixtures",
        uploads_dir=ROOT / "data" / "uploads",
        seed_dir=ROOT / "data" / "seed",
        stage_delay_ms=int(_env("STAGE_DELAY_MS") or 0),
        admin_token=_env("ADMIN_TOKEN"),
        cors_origins=tuple(o.strip() for o in (_env("CORS_ORIGINS") or
                                               "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()),
    )


MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # A49


# ---------------------------------------------------------------------------
# Rule thresholds. Each cites its assumption in docs/assumptions.md.
# ---------------------------------------------------------------------------


class T:
    SCANNED_CHARS_PER_PAGE = 50  # A8
    ARITH_TOLERANCE = Decimal("1.00")  # A14
    LOW_CONFIDENCE = 0.70  # A12
    MAX_INVOICE_AGE_DAYS = 180  # A15
    VENDOR_FUZZY_MIN = 90  # A16
    PO_INFER_MIN_SCORE = 0.75  # A21
    PO_INFER_MIN_MARGIN = 0.15  # A21
    PO_INFER_W_BALANCE = 0.6  # A21
    PO_INFER_W_DESC = 0.4  # A21
    AMOUNT_TOL_PCT = Decimal("0.02")  # A23
    AMOUNT_TOL_MIN = Decimal("500.00")  # A23
    UNIT_PRICE_VARIANCE = Decimal("0.05")  # A24
    PO_LINE_PAIR_MIN = 80  # A24
    DUP_TOTAL_TOLERANCE = Decimal("1.00")  # A25
    DUP_DATE_WINDOW_DAYS = 7  # A25
    DUP_NUMBER_SIMILARITY = 85  # A25
    DEFAULT_GST_RATE = Decimal("18")  # A36 fallback when the invoice shows no rate
