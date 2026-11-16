"""Storage. SQLite by default; set DATABASE_URL for PostgreSQL."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA_DIR = Path(os.environ.get("KARSAATHI_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
BILL_STORE = DATA_DIR / "bills"
BILL_STORE.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'karsaathi.db').as_posix()}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
                       json_serializer=lambda o: json.dumps(o, default=str, ensure_ascii=False))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str] = mapped_column(String(15), unique=True)
    city: Mapped[str] = mapped_column(String(60), default="")
    scheme: Mapped[str] = mapped_column(String(10), default="MONTHLY")  # MONTHLY | QRMP
    aato_cr: Mapped[float] = mapped_column(Float, default=1.0)          # aggregate turnover, crore
    bank_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_on: Mapped[date] = mapped_column(Date, default=date(2020, 1, 1))
    owner_phone: Mapped[str] = mapped_column(String(20), default="")
    language: Mapped[str] = mapped_column(String(5), default="en")


class Party(Base):
    """Suppliers and customers."""
    __tablename__ = "parties"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    role: Mapped[str] = mapped_column(String(10), default="supplier")
    # days after the 11th each month's GSTR-1 was filed; null = missed that month
    filing_history: Mapped[list] = mapped_column(JSON, default=list)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))           # sale | purchase
    channel: Mapped[str] = mapped_column(String(20))        # whatsapp_photo | whatsapp_pdf | whatsapp_text | voice | upi_sms | seed
    method: Mapped[str] = mapped_column(String(10))         # qr | ocr | llm | text | manual | seed
    status: Mapped[str] = mapped_column(String(10), default="booked")  # booked | review | rejected
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    inv_no: Mapped[str] = mapped_column(String(40), default="")
    inv_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    party_name: Mapped[str] = mapped_column(String(120), default="")
    party_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pos: Mapped[str] = mapped_column(String(2), default="")  # place of supply state code
    hsn: Mapped[str] = mapped_column(String(8), default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    qty: Mapped[float] = mapped_column(Float, default=0)
    taxable: Mapped[float] = mapped_column(Float, default=0)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    cgst: Mapped[float] = mapped_column(Float, default=0)
    sgst: Mapped[float] = mapped_column(Float, default=0)
    igst: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    rcm: Mapped[bool] = mapped_column(Boolean, default=False)
    itc_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    itc_note: Mapped[str] = mapped_column(String(200), default="")
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    irn: Mapped[str | None] = mapped_column(String(80), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_conf: Mapped[dict] = mapped_column(JSON, default=dict)   # field -> {conf, method}
    issues: Mapped[list] = mapped_column(JSON, default=list)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)  # what to ask the owner
    rule_version: Mapped[str] = mapped_column(String(20), default="")
    cites: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ImsAction(Base):
    __tablename__ = "ims_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    supplier_gstin: Mapped[str] = mapped_column(String(15))
    inv_no: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(10))  # accept | reject | pending
    by: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class EwayBill(Base):
    __tablename__ = "eway_bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | generated | expired | extended
    vehicle_no: Mapped[str | None] = mapped_column(String(15), nullable=True)
    transporter_phone: Mapped[str] = mapped_column(String(20), default="")
    distance_km: Mapped[int] = mapped_column(Integer, default=0)
    ewb_no: Mapped[str | None] = mapped_column(String(14), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    km_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ReturnDraft(Base):
    __tablename__ = "returns"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    period: Mapped[str] = mapped_column(String(6))     # MMYYYY
    form: Mapped[str] = mapped_column(String(10))      # GSTR-3B | PMT-06 | GSTR-1
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | prepared | approved | filed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    maker: Mapped[str | None] = mapped_column(String(40), nullable=True)
    maker_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checker: Mapped[str | None] = mapped_column(String(40), nullable=True)
    checker_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    arn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Nudge(Base):
    __tablename__ = "nudges"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="drafted")  # drafted | sent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    text: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RuleProposal(Base):
    __tablename__ = "rule_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    advisory: Mapped[str] = mapped_column(Text)
    base_version: Mapped[str] = mapped_column(String(20))
    new_version: Mapped[str] = mapped_column(String(20))
    changes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10), default="proposed")  # proposed | approved | rejected
    approved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    impact: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Message(Base):
    """WhatsApp conversation log (both directions)."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # in | out
    text: Mapped[str] = mapped_column(Text, default="")
    media: Mapped[str | None] = mapped_column(String(300), nullable=True)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60))
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


def init_db():
    Base.metadata.create_all(engine)


def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
