"""SQLAlchemy models. Money columns store Decimal as text so SQLite never rounds through float."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Money(TypeDecorator[Decimal]):
    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend. SQLite drops tzinfo, so it is restored on read."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Vendor(Base):
    __tablename__ = "vendors"
    vendor_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    gstin: Mapped[str] = mapped_column(String(15), index=True)
    status: Mapped[str] = mapped_column(String(16))
    bank_account: Mapped[str] = mapped_column(String(32))
    ifsc: Mapped[str] = mapped_column(String(11))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(64))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    po_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.vendor_id"), index=True)
    issue_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    total_amount: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16))
    lines: Mapped[list[POLine]] = relationship(order_by="POLine.line_no", cascade="all, delete-orphan")


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(ForeignKey("purchase_orders.po_number"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    hsn_sac: Mapped[str] = mapped_column(String(16))
    qty: Mapped[Decimal] = mapped_column(Money)
    unit: Mapped[str] = mapped_column(String(16))
    unit_price: Mapped[Decimal] = mapped_column(Money)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), index=True)
    decision: Mapped[str | None] = mapped_column(String(16), index=True)
    flags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    normalized_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    explanation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    matched_po: Mapped[str | None] = mapped_column(String(32), index=True)
    po_match_type: Mapped[str | None] = mapped_column(String(16))  # EXPLICIT / INFERRED
    vendor_id: Mapped[str | None] = mapped_column(String(16), index=True)
    vendor_key: Mapped[str | None] = mapped_column(String(64), index=True)  # A26
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    invoice_number_canonical: Mapped[str | None] = mapped_column(String(64), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Money)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    reviewer_action: Mapped[str | None] = mapped_column(String(16))  # APPROVE / REJECT
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    events: Mapped[list[StageEvent]] = relationship(order_by="StageEvent.seq", cascade="all, delete-orphan")
    rules: Mapped[list[RuleResultRow]] = relationship(order_by="RuleResultRow.id", cascade="all, delete-orphan")

    @property
    def effective_decision(self) -> str | None:
        """Reviewer override wins over the automated decision (A30)."""
        if self.reviewer_action == "APPROVE":
            return "APPROVED"
        if self.reviewer_action == "REJECT":
            return "REJECTED"
        return self.decision


class StageEvent(Base):
    __tablename__ = "stage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RuleResultRow(Base):
    __tablename__ = "rule_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16))
    rule_id: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(8))
    severity: Mapped[str] = mapped_column(String(8))
    review_reason: Mapped[bool] = mapped_column(default=False)
    flag: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RunFile(Base):
    """Uploaded PDF bytes, keyed by SHA-256. Kept in the database because container disks are wiped on
    restart (A62). Identical uploads share one row."""

    __tablename__ = "run_files"
    file_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
