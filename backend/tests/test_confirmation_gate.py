"""
tests/test_confirmation_gate.py
─────────────────────────────────
Tests that execute_action cannot fire without a valid confirmation token.
"""

from __future__ import annotations

import time
import uuid

import pytest
from jose import jwt

from app.config import get_settings

settings = get_settings()


def _make_valid_token(action_type: str = "create_escalation", payload: dict | None = None) -> str:
    """Create a valid, unexpired JWT action token."""
    idempotency_key = str(uuid.uuid4())
    claims = {
        "action_type": action_type,
        "payload": payload or {"ticket_id": "TKT-9999", "reason": "test"},
        "account_id": "ACCT-001",
        "idempotency_key": idempotency_key,
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    return jwt.encode(claims, settings.action_token_secret, algorithm="HS256")


def _make_expired_token() -> str:
    """Create a JWT token that is already expired."""
    claims = {
        "action_type": "create_escalation",
        "payload": {"ticket_id": "TKT-9999"},
        "account_id": "ACCT-001",
        "idempotency_key": str(uuid.uuid4()),
        "exp": int(time.time()) - 60,  # expired 1 minute ago
        "iat": int(time.time()) - 360,
    }
    return jwt.encode(claims, settings.action_token_secret, algorithm="HS256")


# ── Test 1: No token → error ──────────────────────────────────────────────────

def test_execute_action_with_no_token_fails():
    """Calling execute_action with an empty/garbage token must return an error."""
    from app.tools.actions import execute_action

    result = execute_action.invoke({"confirmation_token": "not-a-real-token"})

    assert result.get("error") == "invalid_token", (
        f"Expected invalid_token error, got: {result}"
    )


# ── Test 2: Expired token → error ─────────────────────────────────────────────

def test_execute_action_with_expired_token_fails():
    """An expired token must return an invalid_token error."""
    from app.tools.actions import execute_action

    expired = _make_expired_token()
    result = execute_action.invoke({"confirmation_token": expired})

    assert result.get("error") == "invalid_token"
    assert "expired" in result.get("detail", "").lower() or "invalid" in result.get("detail", "").lower()


# ── Test 3: Valid token → success ─────────────────────────────────────────────

def test_execute_action_with_valid_token_succeeds():
    """A valid, unexpired token must execute the action successfully."""
    from app.tools.actions import execute_action

    token = _make_valid_token()
    result = execute_action.invoke({"confirmation_token": token})

    assert result.get("success") is True
    assert result.get("action_type") == "create_escalation"
    assert result.get("executed_at") is not None


# ── Test 4: Idempotency — replay doesn't double-fire ─────────────────────────

def test_execute_action_idempotent_on_replay():
    """
    Submitting the same valid token twice must:
    - Succeed on both calls
    - Return the cached result on the second call (no double execution)
    - Second result contains [IDEMPOTENT] marker
    """
    from app.tools.actions import execute_action, _executed_tokens

    token = _make_valid_token(
        action_type="create_escalation",
        payload={"ticket_id": "TKT-IDEMPOTENT-TEST"},
    )

    result1 = execute_action.invoke({"confirmation_token": token})
    result2 = execute_action.invoke({"confirmation_token": token})

    assert result1.get("success") is True
    assert result2.get("success") is True
    assert "[IDEMPOTENT]" in result2.get("message", ""), (
        "Second execution must return idempotency marker"
    )
    # executed_at must be the same on both calls
    assert result1.get("executed_at") == result2.get("executed_at"), (
        "Idempotent replays must return the same execution timestamp"
    )


# ── Test 5: Wrong secret → error ──────────────────────────────────────────────

def test_execute_action_wrong_secret_fails():
    """Token signed with a different secret must be rejected."""
    from app.tools.actions import execute_action

    claims = {
        "action_type": "create_escalation",
        "payload": {"ticket_id": "TKT-9999"},
        "account_id": "ACCT-001",
        "idempotency_key": str(uuid.uuid4()),
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    bad_token = jwt.encode(claims, "wrong-secret-entirely", algorithm="HS256")
    result = execute_action.invoke({"confirmation_token": bad_token})

    assert result.get("error") == "invalid_token"
