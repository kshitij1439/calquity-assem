"""
app/auth/context.py
────────────────────
Mocked authentication / role context.
In production this would validate JWT tokens from an IdP.
For the assessment: account context is injected via HTTP headers
set by the frontend account-switcher dropdown.

Headers consumed:
  X-Account-ID  : e.g. "ACCT-001"
  X-User-Role   : "staff" (internal) | "customer" (external)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class UserContext:
    account_id: str
    role: Literal["staff", "customer"]

    @property
    def is_staff(self) -> bool:
        return self.role == "staff"

    @property
    def effective_account_id(self) -> str:
        """
        Staff can access all accounts ('*' sentinel bypasses repo scoping).
        Customers are scoped to their own account only.
        """
        return "*" if self.is_staff else self.account_id


# Valid mock accounts
_VALID_ACCOUNTS = {"ACCT-001", "ACCT-002"}
_VALID_ROLES = {"staff", "customer"}


async def get_user_context(
    x_account_id: str = Header(..., description="Active account ID (e.g. ACCT-001)"),
    x_user_role: str = Header(default="customer", description="staff | customer"),
) -> UserContext:
    """
    FastAPI dependency that validates and returns the user context.
    Raises 401 for unknown accounts, 400 for invalid roles.
    """
    if x_account_id not in _VALID_ACCOUNTS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unknown account: {x_account_id!r}. Valid accounts: {sorted(_VALID_ACCOUNTS)}",
        )
    if x_user_role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {x_user_role!r}. Must be 'staff' or 'customer'.",
        )
    return UserContext(account_id=x_account_id, role=x_user_role)
