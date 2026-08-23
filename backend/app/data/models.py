"""
app/data/models.py
──────────────────
SQLAlchemy ORM models mapped from ParcelPilot_Assessment_Data.xlsx.
Column names are kept close to the workbook headers for traceability.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class PlanType(str, enum.Enum):
    standard = "Standard"
    growth = "Growth"
    enterprise = "Enterprise"


class OrderStatus(str, enum.Enum):
    draft = "DRAFT"
    booked = "BOOKED"
    picked_up = "PICKED_UP"
    delivered = "DELIVERED"
    cancelled = "CANCELLED"


class TicketSeverity(str, enum.Enum):
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"


class TicketStatus(str, enum.Enum):
    open = "Open"
    in_progress = "In Progress"
    resolved = "Resolved"
    escalated = "Escalated"
    closed = "Closed"


# ── Account ───────────────────────────────────────────────────────────────────

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. ACCT-001
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[PlanType] = mapped_column(Enum(PlanType), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    csm_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="account")
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account {self.id} {self.name!r} plan={self.plan}>"


# ── Order ─────────────────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. ORD-1001
    account_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("accounts.id"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False)
    carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipment_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    destination_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carrier_fault: Mapped[bool | None] = mapped_column(nullable=True)  # None = unknown

    account: Mapped["Account"] = relationship("Account", back_populates="orders")
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order {self.id} status={self.status} account={self.account_id}>"


# ── Ticket ────────────────────────────────────────────────────────────────────

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. TKT-5001
    account_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("accounts.id"), nullable=False, index=True
    )
    order_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("orders.id"), nullable=True, index=True
    )
    severity: Mapped[TicketSeverity] = mapped_column(Enum(TicketSeverity), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_issue_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. KI-208
    issue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship("Account", back_populates="tickets")
    order: Mapped["Order | None"] = relationship("Order", back_populates="tickets")

    def __repr__(self) -> str:
        return f"<Ticket {self.id} {self.severity} status={self.status} account={self.account_id}>"
