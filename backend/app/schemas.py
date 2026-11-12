"""Pydantic models for every piece of IO: LLM extraction, normalized invoice, rules, events."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"


class StageStatus(StrEnum):
    RUNNING = "RUNNING"
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class Outcome(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"  # recorded so no check is silent (A40)


class Severity(StrEnum):
    INFO = "INFO"
    SOFT = "SOFT"
    HARD = "HARD"


class Decision(StrEnum):
    APPROVED = "APPROVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class Flag(StrEnum):
    FRAUD_RISK = "FRAUD_RISK"
    PO_INFERRED = "PO_INFERRED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OVER_PO = "OVER_PO"
    DUPLICATE = "DUPLICATE"


class Stage(StrEnum):
    INGEST = "ingest"
    EXTRACT = "extract"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    VENDOR = "vendor"
    PO_MATCH = "po_match"
    AMOUNT = "amount"
    DUPLICATES = "duplicates"
    DECIDE = "decide"
    EXPLAIN = "explain"


STAGE_ORDER: list[Stage] = list(Stage)

# ---------------------------------------------------------------------------
# LLM extraction schema (sent to Gemini as response_schema)
# ---------------------------------------------------------------------------


def _clamp_confidence(v: float) -> float:
    """Models sometimes answer on a 0 to 100 scale or slightly outside 0 to 1. Bring it into 0 to 1."""
    if v >= 2:  # clearly a percentage, e.g. 95
        v = v / 100
    return min(max(v, 0.0), 1.0)  # small overshoots like 1.05 become 1.0


class _Confident(BaseModel):
    @field_validator("confidence", mode="after", check_fields=False)
    @classmethod
    def _clamp(cls, v: float) -> float:
        return _clamp_confidence(v)


class TextField(_Confident):
    value: str | None = Field(description="The value, or null if it is not printed on the invoice.")
    confidence: float = Field(description="0 to 1. How sure you are the value is read correctly.")
    source_text: str | None = Field(description="The exact snippet on the page the value was read from.")


class BoolField(_Confident):
    value: bool | None
    confidence: float
    source_text: str | None


class ExtractedLine(_Confident):
    description: str | None
    qty: str | None
    unit_price: str | None
    amount: str | None
    confidence: float


class ExtractedTax(_Confident):
    type: str | None = Field(description="CGST, SGST, IGST or other tax name.")
    rate: str | None = Field(description="Percentage as a number, e.g. '9' for 9%.")
    amount: str | None
    confidence: float


class Extraction(BaseModel):
    vendor_name: TextField
    vendor_gstin: TextField
    invoice_number: TextField
    invoice_date: TextField
    due_date: TextField
    po_reference: TextField
    currency: TextField
    line_items: list[ExtractedLine]
    subtotal: TextField
    taxes: list[ExtractedTax]
    tax_inclusive: BoolField
    total: TextField
    bank_account: TextField
    ifsc: TextField


TOP_LEVEL_FIELDS = [
    "vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "due_date", "po_reference",
    "currency", "subtotal", "tax_inclusive", "total", "bank_account", "ifsc",
]
REQUIRED_FIELDS = ["vendor_name", "invoice_number", "invoice_date", "total"]  # A12

# ---------------------------------------------------------------------------
# Normalized invoice
# ---------------------------------------------------------------------------


class NormLine(BaseModel):
    description: str
    qty: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


class NormTax(BaseModel):
    type: str
    rate: Decimal | None
    amount: Decimal | None


class NormalizedInvoice(BaseModel):
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_number_canonical: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    po_reference: str | None = None
    po_reference_canonical: str | None = None
    currency: str | None = None
    line_items: list[NormLine] = []
    subtotal: Decimal | None = None
    taxes: list[NormTax] = []
    tax_inclusive: bool = False
    total: Decimal | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    confidence: dict[str, float] = {}

    @property
    def tax_total(self) -> Decimal | None:
        amounts = [t.amount for t in self.taxes if t.amount is not None]
        return sum(amounts, Decimal("0.00")) if amounts else None

    @property
    def tax_rate(self) -> Decimal | None:
        rates = [t.rate for t in self.taxes if t.rate is not None]
        return sum(rates, Decimal("0")) if rates else None


# ---------------------------------------------------------------------------
# Rules, stages, decisions
# ---------------------------------------------------------------------------


class RuleResult(BaseModel):
    rule_id: str
    stage: Stage
    outcome: Outcome
    severity: Severity
    message: str
    evidence: dict[str, Any] = {}
    review_reason: bool = False
    flag: Flag | None = None


class StageResult(BaseModel):
    """What a stage function returns. The runner turns it into a StageEvent."""

    stage: Stage
    message: str
    payload: dict[str, Any] = {}
    rules: list[RuleResult] = []
    skipped: bool = False
    status_override: StageStatus | None = None

    @property
    def status(self) -> StageStatus:
        if self.status_override is not None:
            return self.status_override
        if self.skipped:
            return StageStatus.SKIPPED
        outcomes = {r.outcome for r in self.rules}
        if Outcome.FAIL in outcomes:
            return StageStatus.FAIL
        if Outcome.WARN in outcomes:
            return StageStatus.WARN
        return StageStatus.PASS


class StageEventOut(BaseModel):
    run_id: str
    seq: int
    stage: Stage
    status: StageStatus
    message: str
    started_at: datetime
    ended_at: datetime | None
    payload: dict[str, Any] = {}


class DecisionResult(BaseModel):
    decision: Decision
    flags: list[Flag]
    hard_fails: list[str]
    soft_fails: list[str]
    review_warnings: list[str]


class Explanation(BaseModel):
    verdict: str
    why: list[str]
    next_actions: list[str]


# ---------------------------------------------------------------------------
# Reference data handed to pure stage functions
# ---------------------------------------------------------------------------


class VendorRec(BaseModel):
    vendor_id: str
    legal_name: str
    aliases: list[str]
    gstin: str
    status: str
    bank_account: str
    ifsc: str
    email: str
    phone: str


class POLineRec(BaseModel):
    line_no: int
    description: str
    qty: Decimal
    unit: str
    unit_price: Decimal


class PORec(BaseModel):
    po_number: str
    vendor_id: str
    status: str
    currency: str
    total: Decimal
    consumed: Decimal
    lines: list[POLineRec]

    @property
    def remaining(self) -> Decimal:
        return self.total - self.consumed


class PriorRun(BaseModel):
    run_id: str
    filename: str
    file_hash: str
    vendor_key: str | None
    invoice_number: str | None
    invoice_number_canonical: str | None
    invoice_date: date | None
    total: Decimal | None
