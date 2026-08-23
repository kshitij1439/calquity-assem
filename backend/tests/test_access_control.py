"""
tests/test_access_control.py
──────────────────────────────
Tests that cross-account access always returns AccessDenied,
never data, never a 500 error.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.data.repository import AccessDenied


# ── Helper: mock DB session ───────────────────────────────────────────────────

def _make_mock_order(order_id: str, account_id: str):
    order = MagicMock()
    order.id = order_id
    order.account_id = account_id
    order.status = MagicMock()
    order.status.value = "BOOKED"
    return order


def _make_mock_account(account_id: str, name: str, plan: str):
    account = MagicMock()
    account.id = account_id
    account.name = name
    account.plan = MagicMock()
    account.plan.value = plan
    return account


# ── Test 1: Cross-account order access ────────────────────────────────────────

def test_get_order_cross_account_returns_access_denied():
    """
    Northstar (ACCT-001) requesting a LumenWorks (ACCT-002) order
    must return AccessDenied, not the order.
    """
    from app.data.repository import get_order

    lumenworks_order = _make_mock_order("ORD-2001", "ACCT-002")

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = lumenworks_order

    result = get_order("ORD-2001", requesting_account_id="ACCT-001", db=mock_db)

    assert isinstance(result, AccessDenied), (
        f"Expected AccessDenied, got {type(result).__name__}: {result}"
    )
    assert result.requester_account_id == "ACCT-001"
    assert "ORD-2001" in result.requested_resource


def test_get_order_own_account_returns_order():
    """Accessing your own order should succeed."""
    from app.data.repository import get_order

    northstar_order = _make_mock_order("ORD-1001", "ACCT-001")

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = northstar_order

    result = get_order("ORD-1001", requesting_account_id="ACCT-001", db=mock_db)

    assert not isinstance(result, AccessDenied)
    assert result.id == "ORD-1001"


def test_staff_can_access_any_order():
    """Staff (requesting_account_id='*') can access any account's order."""
    from app.data.repository import get_order

    lumenworks_order = _make_mock_order("ORD-2001", "ACCT-002")

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = lumenworks_order

    result = get_order("ORD-2001", requesting_account_id="*", db=mock_db)

    assert not isinstance(result, AccessDenied)
    assert result.id == "ORD-2001"


# ── Test 2: Cross-account account access ─────────────────────────────────────

def test_get_account_cross_account_returns_access_denied():
    """Customer cannot fetch another account's details."""
    from app.data.repository import get_account

    mock_db = MagicMock()
    result = get_account("ACCT-002", requesting_account_id="ACCT-001", db=mock_db)

    assert isinstance(result, AccessDenied)
    assert result.requester_account_id == "ACCT-001"


def test_get_account_own_account_succeeds():
    """Customer can fetch their own account."""
    from app.data.repository import get_account

    northstar = _make_mock_account("ACCT-001", "Northstar Logistics", "Enterprise")

    mock_db = MagicMock()
    mock_db.get.return_value = northstar

    result = get_account("ACCT-001", requesting_account_id="ACCT-001", db=mock_db)

    assert not isinstance(result, AccessDenied)
    assert result.id == "ACCT-001"


# ── Test 3: Cross-account ticket listing ─────────────────────────────────────

def test_list_tickets_cross_account_returns_access_denied():
    """Cannot list tickets for a different account."""
    from app.data.repository import list_tickets

    mock_db = MagicMock()
    result = list_tickets(
        requesting_account_id="ACCT-001",
        db=mock_db,
        account_id="ACCT-002",
    )

    assert isinstance(result, AccessDenied)


# ── Test 4: AccessDenied serialises correctly ─────────────────────────────────

def test_access_denied_to_dict():
    """AccessDenied.to_dict() must contain the error field for API responses."""
    ad = AccessDenied(
        reason="Cross-account access not permitted.",
        requested_resource="order:ORD-2001",
        requester_account_id="ACCT-001",
    )
    d = ad.to_dict()
    assert d["error"] == "access_denied"
    assert "ACCT-001" in d["requester_account_id"]
    assert "ORD-2001" in d["requested_resource"]


# ── Test 5: Auth context header validation ────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_account_header_returns_401():
    """Unknown account in X-Account-ID header must return 401."""
    from app.auth.context import get_user_context
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_user_context(x_account_id="ACCT-999", x_user_role="customer")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_account_header_returns_context():
    """Valid account + role returns a UserContext."""
    from app.auth.context import get_user_context

    ctx = await get_user_context(x_account_id="ACCT-001", x_user_role="customer")
    assert ctx.account_id == "ACCT-001"
    assert ctx.effective_account_id == "ACCT-001"


@pytest.mark.asyncio
async def test_staff_role_gets_wildcard_account():
    """Staff role returns effective_account_id='*'."""
    from app.auth.context import get_user_context

    ctx = await get_user_context(x_account_id="ACCT-001", x_user_role="staff")
    assert ctx.is_staff
    assert ctx.effective_account_id == "*"
