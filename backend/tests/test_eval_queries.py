"""
tests/test_eval_queries.py
───────────────────────────
Evaluation tests for the two example queries from the brief +
at least 3 synthetic variants using different IDs from the workbook.

These tests verify that the system reasons over retrieved data,
not hardcoded answers. No order/ticket/account IDs are hardcoded
in the agent code — only in test parametrize lists below.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── Test 1: Cancellation eligibility logic ────────────────────────────────────

@pytest.mark.parametrize("order_id,account_id,expected_can_cancel,expected_no_fee", [
    # Brief example: Northstar ORD-1001 — contract waiver applies
    ("ORD-1001", "ACCT-001", True, True),
    # Synthetic: another Northstar order — same contract applies
    ("ORD-1002", "ACCT-001", True, True),
    # Synthetic: LumenWorks order booked recently — within 30-min window → no fee
    ("ORD-2001", "ACCT-002", True, True),  # booked_at set to recent time in mock
])
def test_cancellation_eligibility(order_id, account_id, expected_can_cancel, expected_no_fee):
    """
    Cancellation logic should apply contract overrides for ACCT-001 (Northstar)
    and SOP timing rules for all others.
    """
    from app.data.repository import check_cancellation_eligibility, CancellationEligibility
    from app.data.models import OrderStatus
    from datetime import datetime, timezone, timedelta
    from app.config import SNAPSHOT_NOW

    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.account_id = account_id
    mock_order.status = OrderStatus.booked
    # Set booked_at to 10 minutes ago (within 30-min window for non-contract accounts)
    mock_order.booked_at = SNAPSHOT_NOW - timedelta(minutes=10)

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_order

    result = check_cancellation_eligibility(order_id, account_id, mock_db)

    assert not isinstance(result, Exception)
    assert result.can_cancel == expected_can_cancel

    if expected_no_fee:
        assert result.fee_applicable is False or result.fee_amount == 0.0

    if account_id == "ACCT-001":
        assert "Northstar" in result.reason or "OVERRIDES DEFAULT POLICY" in result.reason or "Enterprise Agreement" in result.reason


# ── Test 2: Cancellation — PICKED_UP cannot be cancelled ─────────────────────

@pytest.mark.parametrize("order_id,account_id", [
    ("ORD-1005", "ACCT-001"),
    ("ORD-2010", "ACCT-002"),
])
def test_picked_up_order_cannot_be_cancelled(order_id, account_id):
    """PICKED_UP orders must never be cancellable regardless of account."""
    from app.data.repository import check_cancellation_eligibility
    from app.data.models import OrderStatus

    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.account_id = account_id
    mock_order.status = OrderStatus.picked_up

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_order

    result = check_cancellation_eligibility(order_id, account_id, mock_db)

    assert result.can_cancel is False
    assert "PICKED_UP" in result.reason or "return-to-origin" in result.reason


# ── Test 3: SLA breach detection ──────────────────────────────────────────────

@pytest.mark.parametrize("ticket_id,account_id,severity,plan,expected_breach", [
    # Brief example: pickup 3 hours late — should compute SLA correctly
    ("TKT-5001", "ACCT-001", "P1", "Enterprise", True),
    # Synthetic: P3 ticket, no breach expected if recent
    ("TKT-5010", "ACCT-002", "P3", "Growth", False),
    # Synthetic: P2 ticket, Northstar contract target is 60 min
    ("TKT-5020", "ACCT-001", "P2", "Enterprise", False),
])
def test_sla_check(ticket_id, account_id, severity, plan, expected_breach):
    """SLA check must use SNAPSHOT_NOW and contract overrides, not datetime.now()."""
    from app.data.repository import check_sla, SLAStatus
    from app.data.models import TicketSeverity, TicketStatus
    from app.config import SNAPSHOT_NOW
    from datetime import timedelta

    mock_ticket = MagicMock()
    mock_ticket.id = ticket_id
    mock_ticket.account_id = account_id
    mock_ticket.severity = TicketSeverity(severity)
    mock_ticket.status = TicketStatus.open
    mock_ticket.first_response_at = None

    # Set created_at to force breach/no-breach
    if expected_breach:
        # Created 500 minutes ago — any P1/P2 target will be exceeded
        mock_ticket.created_at = SNAPSHOT_NOW - timedelta(minutes=500)
    else:
        # Created 5 minutes ago — no breach
        mock_ticket.created_at = SNAPSHOT_NOW - timedelta(minutes=5)

    mock_account = MagicMock()
    mock_account.plan = MagicMock()
    mock_account.plan.value = plan

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_ticket
    mock_db.get.return_value = mock_account

    result = check_sla(ticket_id, account_id, mock_db)

    assert isinstance(result, SLAStatus)
    assert result.is_breached == expected_breach


# ── Test 4: No hardcoded IDs in repository ───────────────────────────────────

def test_repository_does_not_hardcode_ids():
    """
    The repository must not contain any hardcoded order/account/ticket IDs.
    This test scans the source file.
    """
    import re
    from pathlib import Path

    repo_file = Path(__file__).parent.parent / "app" / "data" / "repository.py"
    source = repo_file.read_text()

    # Check for hardcoded example IDs from the brief
    hardcoded_patterns = [
        r'"ORD-1001"',
        r'"ACCT-001"',
        r'"TKT-5001"',
        r"'ORD-1001'",
        r"'ACCT-001'",
    ]

    for pattern in hardcoded_patterns:
        # Allow in comments (lines starting with #)
        non_comment_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        ]
        non_comment_source = "\n".join(non_comment_lines)
        assert not re.search(pattern, non_comment_source), (
            f"Hardcoded ID pattern {pattern!r} found in repository.py — "
            "all IDs must come from function parameters."
        )


# ── Test 5: Contract overrides detected ───────────────────────────────────────

def test_northstar_contract_sla_override():
    """
    For ACCT-001 (Northstar), resolve_sla_target_minutes must return
    15 min for P1 (from contract), not 30 min (from default Enterprise policy).
    """
    from app.data.repository import resolve_sla_target_minutes

    # Northstar contract: P1 = 15 min
    target = resolve_sla_target_minutes("ACCT-001", "P1", "Enterprise")
    assert target == 15, (
        f"Northstar P1 SLA should be 15 min (contract), got {target} min"
    )


def test_lumenworks_contract_sla_override():
    """
    For ACCT-002 (LumenWorks), P1 = 120 min (contract), not 30 min (Growth default).
    """
    from app.data.repository import resolve_sla_target_minutes

    target = resolve_sla_target_minutes("ACCT-002", "P1", "Growth")
    assert target == 120, (
        f"LumenWorks P1 SLA should be 120 min (contract), got {target} min"
    )


def test_unknown_account_falls_back_to_plan_default():
    """Accounts with no contract use the plan-based default targets."""
    from app.data.repository import resolve_sla_target_minutes

    target = resolve_sla_target_minutes("ACCT-999", "P1", "Standard")
    assert target == 240, (
        f"Standard P1 SLA should be 240 min, got {target} min"
    )
