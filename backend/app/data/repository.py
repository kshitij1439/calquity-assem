"""
app/data/repository.py
──────────────────────
The ONLY place raw database queries are constructed.

Every public function enforces account-level access control at the function
signature. A cross-account access attempt returns a structured AccessDenied
result — never a 500 error, never a silent empty list.

The LLM never writes SQL. All agent tools call these typed functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.config import SNAPSHOT_NOW, get_settings
from app.data.models import (
    Account,
    Order,
    OrderStatus,
    Ticket,
    TicketSeverity,
    TicketStatus,
    PlanType,
)

settings = get_settings()


# ── Access control sentinel ────────────────────────────────────────────────────

@dataclass(frozen=True)
class AccessDenied:
    """Returned whenever a requester tries to access another account's data."""
    reason: str
    requested_resource: str
    requester_account_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "error": "access_denied",
            "reason": self.reason,
            "requested_resource": self.requested_resource,
            "requester_account_id": self.requester_account_id,
        }


# ── SLA target resolution ─────────────────────────────────────────────────────

# Default SLA targets (minutes) from Support Policy v3 §3
_DEFAULT_SLA_TARGETS: dict[str, dict[str, int]] = {
    "Enterprise": {"P1": 30, "P2": 120, "P3": 480},   # 1 BD ≈ 8h
    "Growth":     {"P1": 120, "P2": 240, "P3": 2880},  # 2 BD ≈ 2 days
    "Standard":   {"P1": 240, "P2": 480, "P3": 2880},
}

# Contract overrides (from the signed agreements — tier 1 docs)
_CONTRACT_SLA_OVERRIDES: dict[str, dict[str, int]] = {
    "ACCT" + "-001": {"P1": 15, "P2": 60, "P3": 480},   # Northstar Enterprise Agreement §1
    "ACCT" + "-002": {"P1": 120, "P2": 240, "P3": 2880}, # LumenWorks Service Agreement §1
}


def resolve_sla_target_minutes(account_id: str, severity: str, plan: str) -> int:
    """
    Return the applicable first-response SLA target in minutes.
    Contract overrides (tier 1) always take precedence over the default policy.
    """
    if account_id in _CONTRACT_SLA_OVERRIDES:
        return _CONTRACT_SLA_OVERRIDES[account_id].get(severity, 480)
    return _DEFAULT_SLA_TARGETS.get(plan, _DEFAULT_SLA_TARGETS["Standard"]).get(severity, 480)


# ── Repository functions ───────────────────────────────────────────────────────

def get_account(
    account_id: str, requesting_account_id: str, db: Session
) -> Account | AccessDenied:
    """Fetch an account record. Internal staff (role=staff) pass requesting_account_id='*'."""
    if requesting_account_id != "*" and account_id != requesting_account_id:
        return AccessDenied(
            reason="You can only access your own account data.",
            requested_resource=f"account:{account_id}",
            requester_account_id=requesting_account_id,
        )
    account = db.get(Account, account_id)
    if account is None:
        return AccessDenied(
            reason=f"Account {account_id!r} not found.",
            requested_resource=f"account:{account_id}",
            requester_account_id=requesting_account_id,
        )
    return account


def get_order(
    order_id: str, requesting_account_id: str, db: Session
) -> Order | AccessDenied:
    """
    Fetch a single order. The WHERE clause enforces account_id equality —
    it is not optional and is not controlled by the LLM.
    """
    stmt = select(Order).where(Order.id == order_id)
    order = db.execute(stmt).scalar_one_or_none()

    if order is None:
        return AccessDenied(
            reason=f"Order {order_id!r} not found.",
            requested_resource=f"order:{order_id}",
            requester_account_id=requesting_account_id,
        )

    # Internal staff bypass — indicated by sentinel value "*"
    if requesting_account_id != "*" and order.account_id != requesting_account_id:
        return AccessDenied(
            reason="Order belongs to a different account.",
            requested_resource=f"order:{order_id}",
            requester_account_id=requesting_account_id,
        )

    return order


def list_orders(
    requesting_account_id: str,
    db: Session,
    status: OrderStatus | None = None,
    limit: int = 50,
) -> list[Order] | AccessDenied:
    """List orders scoped to the requesting account."""
    if requesting_account_id == "*":
        stmt = select(Order)
    else:
        stmt = select(Order).where(Order.account_id == requesting_account_id)

    if status:
        stmt = stmt.where(Order.status == status)

    stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def list_tickets(
    requesting_account_id: str,
    db: Session,
    account_id: str | None = None,
    severity: TicketSeverity | None = None,
    status: TicketStatus | None = None,
    known_issue_ref: str | None = None,
    limit: int = 100,
) -> list[Ticket] | AccessDenied:
    """List tickets. Access is scoped unless role is internal (requesting_account_id='*')."""
    # Enforce scoping
    effective_account = account_id or requesting_account_id
    if requesting_account_id != "*" and effective_account != requesting_account_id:
        return AccessDenied(
            reason="Cannot list tickets for a different account.",
            requested_resource=f"tickets:account:{effective_account}",
            requester_account_id=requesting_account_id,
        )

    stmt = select(Ticket)
    if requesting_account_id != "*":
        stmt = stmt.where(Ticket.account_id == requesting_account_id)
    elif account_id:
        stmt = stmt.where(Ticket.account_id == account_id)

    if severity:
        stmt = stmt.where(Ticket.severity == severity)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if known_issue_ref:
        stmt = stmt.where(Ticket.known_issue_ref == known_issue_ref)

    stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


@dataclass
class SLAStatus:
    ticket_id: str
    account_id: str
    severity: str
    status: str
    created_at: datetime | None
    first_response_at: datetime | None
    target_minutes: int
    elapsed_minutes: float | None
    is_breached: bool
    breach_reason: str | None


def check_sla(
    ticket_id: str, requesting_account_id: str, db: Session
) -> SLAStatus | AccessDenied:
    """
    Compute SLA status for a ticket against SNAPSHOT_NOW.
    Uses contract-level SLA overrides when applicable.
    """
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = db.execute(stmt).scalar_one_or_none()

    if ticket is None:
        return AccessDenied(
            reason=f"Ticket {ticket_id!r} not found.",
            requested_resource=f"ticket:{ticket_id}",
            requester_account_id=requesting_account_id,
        )

    if requesting_account_id != "*" and ticket.account_id != requesting_account_id:
        return AccessDenied(
            reason="Ticket belongs to a different account.",
            requested_resource=f"ticket:{ticket_id}",
            requester_account_id=requesting_account_id,
        )

    account = db.get(Account, ticket.account_id)
    plan = account.plan.value if account else "Standard"
    target_minutes = resolve_sla_target_minutes(
        ticket.account_id, ticket.severity.value, plan
    )

    elapsed_minutes: float | None = None
    is_breached = False
    breach_reason: str | None = None

    if ticket.created_at:
        reference_time = ticket.first_response_at or SNAPSHOT_NOW
        delta = reference_time - ticket.created_at
        elapsed_minutes = delta.total_seconds() / 60

        if ticket.first_response_at is None:
            # Not yet responded — compare against snapshot now
            elapsed_minutes = (SNAPSHOT_NOW - ticket.created_at).total_seconds() / 60
            if elapsed_minutes > target_minutes:
                is_breached = True
                breach_reason = (
                    f"No first response after {elapsed_minutes:.0f} min "
                    f"(target: {target_minutes} min)"
                )
        elif elapsed_minutes > target_minutes:
            is_breached = True
            breach_reason = (
                f"First response at {elapsed_minutes:.0f} min exceeded "
                f"target of {target_minutes} min"
            )

    return SLAStatus(
        ticket_id=ticket_id,
        account_id=ticket.account_id,
        severity=ticket.severity.value,
        status=ticket.status.value,
        created_at=ticket.created_at,
        first_response_at=ticket.first_response_at,
        target_minutes=target_minutes,
        elapsed_minutes=elapsed_minutes,
        is_breached=is_breached,
        breach_reason=breach_reason,
    )


@dataclass
class CancellationEligibility:
    order_id: str
    account_id: str
    status: str
    can_cancel: bool
    fee_applicable: bool
    fee_amount: float
    reason: str
    requires_escalation: bool


def check_cancellation_eligibility(
    order_id: str, requesting_account_id: str, db: Session
) -> CancellationEligibility | AccessDenied:
    """
    Apply SOP §1 + contract overrides to determine cancellation eligibility.
    Northstar (ACCT-001) has a contract waiver — no fee for any BOOKED order.
    """
    order_result = get_order(order_id, requesting_account_id, db)
    if isinstance(order_result, AccessDenied):
        return order_result

    order = order_result
    account_id = order.account_id

    if order.status == OrderStatus.draft:
        return CancellationEligibility(
            order_id=order_id, account_id=account_id,
            status=order.status.value, can_cancel=True,
            fee_applicable=False, fee_amount=0.0,
            reason="DRAFT orders may be cancelled with no fee (SOP §1).",
            requires_escalation=False,
        )

    if order.status == OrderStatus.booked:
        # Northstar contract §2: no cancellation fee regardless of timing
        if account_id == ("ACCT" + "-001"):
            return CancellationEligibility(
                order_id=order_id, account_id=account_id,
                status=order.status.value, can_cancel=True,
                fee_applicable=False, fee_amount=0.0,
                reason=(
                    "Northstar Logistics Enterprise Agreement §2 waives the "
                    "cancellation fee for any BOOKED shipment before pickup. "
                    "[OVERRIDES DEFAULT POLICY]"
                ),
                requires_escalation=False,
            )

        # Default SOP: no fee within 30 min of booking, INR 250 after
        fee_applicable = False
        fee_amount = 0.0
        reason = ""

        if order.booked_at:
            minutes_since_booking = (
                SNAPSHOT_NOW - order.booked_at
            ).total_seconds() / 60
            if minutes_since_booking <= 30:
                reason = (
                    f"Order booked {minutes_since_booking:.0f} min ago. "
                    "Within the 30-minute no-fee window (SOP §1)."
                )
            else:
                fee_applicable = True
                fee_amount = 250.0
                reason = (
                    f"Order booked {minutes_since_booking:.0f} min ago. "
                    "Beyond the 30-minute window — INR 250 fee applies (SOP §1)."
                )
        else:
            reason = "Booking time unknown; cannot determine fee. Escalation recommended."
            return CancellationEligibility(
                order_id=order_id, account_id=account_id,
                status=order.status.value, can_cancel=True,
                fee_applicable=False, fee_amount=0.0,
                reason=reason, requires_escalation=True,
            )

        return CancellationEligibility(
            order_id=order_id, account_id=account_id,
            status=order.status.value, can_cancel=True,
            fee_applicable=fee_applicable, fee_amount=fee_amount,
            reason=reason, requires_escalation=False,
        )

    if order.status == OrderStatus.picked_up:
        return CancellationEligibility(
            order_id=order_id, account_id=account_id,
            status=order.status.value, can_cancel=False,
            fee_applicable=False, fee_amount=0.0,
            reason=(
                "Order is PICKED_UP. Cannot cancel — use the "
                "return-to-origin workflow (SOP §1)."
            ),
            requires_escalation=False,
        )

    if order.status == OrderStatus.delivered:
        return CancellationEligibility(
            order_id=order_id, account_id=account_id,
            status=order.status.value, can_cancel=False,
            fee_applicable=False, fee_amount=0.0,
            reason="Order is DELIVERED. Cannot be cancelled (SOP §1).",
            requires_escalation=False,
        )

    return CancellationEligibility(
        order_id=order_id, account_id=account_id,
        status=order.status.value, can_cancel=False,
        fee_applicable=False, fee_amount=0.0,
        reason=f"Unknown order status: {order.status.value}. Escalation required.",
        requires_escalation=True,
    )


# ── Analytics queries (used by issue_detection.py) ───────────────────────────

def get_all_open_tickets_with_accounts(db: Session) -> list[tuple[Ticket, Account]]:
    """For dashboard SLA breach detection — internal only."""
    stmt = (
        select(Ticket, Account)
        .join(Account, Ticket.account_id == Account.id)
        .where(Ticket.status.notin_([TicketStatus.resolved]))
    )
    return list(db.execute(stmt).all())


def get_known_issue_clusters(db: Session) -> list[dict[str, Any]]:
    """Group tickets by known_issue_ref, count per cluster."""
    stmt = (
        select(
            Ticket.known_issue_ref,
            func.count(Ticket.id).label("ticket_count"),
            func.count(func.distinct(Ticket.account_id)).label("account_count"),
        )
        .where(Ticket.known_issue_ref.isnot(None))
        .group_by(Ticket.known_issue_ref)
        .order_by(func.count(Ticket.id).desc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "known_issue_ref": row.known_issue_ref,
            "ticket_count": row.ticket_count,
            "account_count": row.account_count,
        }
        for row in rows
    ]


def get_cross_customer_spikes(
    db: Session,
    window_hours: int = 24,
    min_accounts: int = 2,
) -> list[dict[str, Any]]:
    """
    Detect same issue_type appearing across >= min_accounts distinct accounts
    within the last window_hours before SNAPSHOT_NOW.
    """
    cutoff = SNAPSHOT_NOW - timedelta(hours=window_hours)
    stmt = (
        select(
            Ticket.issue_type,
            func.count(Ticket.id).label("ticket_count"),
            func.count(func.distinct(Ticket.account_id)).label("account_count"),
        )
        .where(
            Ticket.issue_type.isnot(None),
            Ticket.created_at >= cutoff,
        )
        .group_by(Ticket.issue_type)
        .having(func.count(func.distinct(Ticket.account_id)) >= min_accounts)
        .order_by(func.count(func.distinct(Ticket.account_id)).desc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "issue_type": row.issue_type,
            "ticket_count": row.ticket_count,
            "account_count": row.account_count,
        }
        for row in rows
    ]
