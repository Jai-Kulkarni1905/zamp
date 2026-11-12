"""Response and request models for the HTTP API. Money is serialized as a string (Decimal), never a float."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RunCreated(BaseModel):
    run_id: str
    status: str
    events_url: str
    detail_url: str


class RunSummary(BaseModel):
    id: str
    filename: str
    status: str
    decision: str | None
    effective_decision: str | None
    flags: list[str]
    vendor_id: str | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    total: Decimal | None
    matched_po: str | None
    po_match_type: str | None
    created_at: datetime
    duration_ms: int | None
    reviewer_action: str | None
    verdict: str | None = Field(None, description="One-line verdict from the explanation, for list views.")


class RunList(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class StageView(BaseModel):
    stage: str
    status: str  # PENDING until the first event arrives
    message: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    payload: dict[str, Any]


class RuleView(BaseModel):
    stage: str
    rule_id: str
    outcome: str
    severity: str
    review_reason: bool
    flag: str | None
    message: str
    evidence: dict[str, Any]


class POBalance(BaseModel):
    po_number: str
    vendor_id: str
    vendor_name: str | None
    status: str
    issue_date: date
    total: Decimal
    consumed: Decimal
    remaining: Decimal


class RunDetail(RunSummary):
    file_hash: str
    error: str | None
    reviewer_note: str | None
    reviewed_at: datetime | None
    explanation: dict[str, Any] | None
    extracted: dict[str, Any] | None
    normalized: dict[str, Any] | None
    stages: list[StageView]
    rules: list[RuleView]
    po: POBalance | None = Field(description="Current balance of the matched PO (after all approvals so far).")
    file_url: str
    events_url: str


class ReviewIn(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("note must not be blank")
        return v.strip()


class POInvoice(BaseModel):
    run_id: str
    filename: str
    invoice_number: str | None
    total: Decimal | None
    decision: str | None
    effective_decision: str | None
    counts_against_po: bool


class POView(POBalance):
    invoices: list[POInvoice]


class VendorView(BaseModel):
    vendor_id: str
    legal_name: str
    aliases: list[str]
    gstin: str
    status: str
    bank_account_masked: str | None
    ifsc: str
    email: str
    phone: str
    state: str


class Stats(BaseModel):
    runs_total: int
    runs_done: int
    runs_error: int
    runs_in_progress: int
    decisions: dict[str, int] = Field(description="Automated decisions of DONE runs.")
    effective_decisions: dict[str, int] = Field(description="After reviewer overrides.")
    approval_rate: float | None = Field(description="Automated APPROVED / DONE runs, 0 to 1.")
    review_queue: int = Field(description="NEEDS_REVIEW runs with no reviewer action yet.")
    avg_processing_ms: int | None
    value_processed: Decimal = Field(description="Sum of invoice totals of DONE runs.")
    value_approved: Decimal = Field(description="Sum of totals whose effective decision is APPROVED.")
    flags: dict[str, int]


class ResetResult(BaseModel):
    runs_removed: int
    seeded: dict[str, int]
