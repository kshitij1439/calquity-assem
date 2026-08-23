"""
app/tools/actions.py
──────────────────────
Tool 3: propose_action + execute_action

propose_action  → draft description + signed JWT confirmation token (5-min TTL)
execute_action  → validates token, runs the action, idempotent on replay

The LLM NEVER calls execute_action directly. It calls propose_action,
and execute_action is only triggered by the frontend submitting a valid token.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.config import get_settings

settings = get_settings()

# ── In-memory idempotency store (production: use Redis/Postgres) ──────────────
_executed_tokens: dict[str, dict[str, Any]] = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProposeActionInput(BaseModel):
    action_type: Literal["create_escalation", "update_ticket", "create_followup_task"] = Field(
        description="Type of state-changing action to propose"
    )
    payload: dict[str, Any] = Field(
        description="Action-specific data (ticket_id, reason, assignee, etc.)"
    )
    account_id: str = Field(description="Account context for the action")


class ActionProposal(BaseModel):
    action_type: str
    payload: dict[str, Any]
    draft_description: str
    confirmation_token: str
    expires_at: str
    idempotency_key: str


class ExecuteActionInput(BaseModel):
    confirmation_token: str = Field(
        description="The token returned by propose_action"
    )


class ActionResult(BaseModel):
    success: bool
    action_type: str
    payload: dict[str, Any]
    message: str
    idempotency_key: str
    executed_at: str | None = None


class ConfirmationError(BaseModel):
    error: str
    detail: str


# ── Helper: human-readable draft descriptions ─────────────────────────────────

def _build_draft_description(action_type: str, payload: dict[str, Any]) -> str:
    if action_type == "create_escalation":
        ticket_id = payload.get("ticket_id", "UNKNOWN")
        reason = payload.get("reason", "No reason provided")
        assignee = payload.get("assignee", "the on-call team")
        return (
            f"Create an escalation for ticket **{ticket_id}**.\n"
            f"Reason: {reason}\n"
            f"This will be assigned to: {assignee}\n"
            f"⚠️ This action requires your confirmation before it is executed."
        )
    if action_type == "update_ticket":
        ticket_id = payload.get("ticket_id", "UNKNOWN")
        updates = payload.get("updates", {})
        return (
            f"Update ticket **{ticket_id}** with the following changes:\n"
            + "\n".join(f"  • {k}: {v}" for k, v in updates.items())
            + "\n⚠️ This action requires your confirmation."
        )
    if action_type == "create_followup_task":
        description = payload.get("description", "No description")
        return (
            f"Create a follow-up task:\n{description}\n"
            "⚠️ This action requires your confirmation."
        )
    return f"Proposed action: {action_type}. ⚠️ Requires confirmation."


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool(args_schema=ProposeActionInput)
def propose_action(
    action_type: str,
    payload: dict[str, Any],
    account_id: str,
) -> dict[str, Any]:
    """
    Propose a state-changing action. Returns a draft description and a
    confirmation token. Does NOT execute the action.
    The token must be submitted by the user via /confirm-action within 5 minutes.
    """
    idempotency_key = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.action_token_ttl_seconds
    )

    token_payload = {
        "action_type": action_type,
        "payload": payload,
        "account_id": account_id,
        "idempotency_key": idempotency_key,
        "exp": int(expires_at.timestamp()),
        "iat": int(time.time()),
    }

    confirmation_token = jwt.encode(
        token_payload,
        settings.action_token_secret,
        algorithm="HS256",
    )

    draft = _build_draft_description(action_type, payload)

    return ActionProposal(
        action_type=action_type,
        payload=payload,
        draft_description=draft,
        confirmation_token=confirmation_token,
        expires_at=expires_at.isoformat(),
        idempotency_key=idempotency_key,
    ).model_dump()


@tool(args_schema=ExecuteActionInput)
def execute_action(confirmation_token: str) -> dict[str, Any]:
    """
    Execute a previously proposed action using a valid, unexpired confirmation token.
    Idempotent: replaying the same token returns the cached result without re-executing.
    """
    # Decode + validate JWT
    try:
        claims = jwt.decode(
            confirmation_token,
            settings.action_token_secret,
            algorithms=["HS256"],
        )
    except JWTError as e:
        return ConfirmationError(
            error="invalid_token",
            detail=f"Token is invalid or expired: {e}",
        ).model_dump()

    action_type = claims["action_type"]
    payload = claims["payload"]
    idempotency_key = claims["idempotency_key"]

    # Idempotency check: already executed?
    if idempotency_key in _executed_tokens:
        cached = _executed_tokens[idempotency_key]
        return ActionResult(
            success=True,
            action_type=action_type,
            payload=payload,
            message=f"[IDEMPOTENT] Action was already executed at {cached['executed_at']}.",
            idempotency_key=idempotency_key,
            executed_at=cached["executed_at"],
        ).model_dump()

    # ── Mock execution (replace with real integrations in production) ─────────
    executed_at = datetime.now(timezone.utc).isoformat()
    result_message = _mock_execute(action_type, payload)

    # Record execution for idempotency
    _executed_tokens[idempotency_key] = {
        "action_type": action_type,
        "payload": payload,
        "executed_at": executed_at,
    }

    return ActionResult(
        success=True,
        action_type=action_type,
        payload=payload,
        message=result_message,
        idempotency_key=idempotency_key,
        executed_at=executed_at,
    ).model_dump()


def _mock_execute(action_type: str, payload: dict[str, Any]) -> str:
    """Mock execution layer. Replace with real API calls in production."""
    if action_type == "create_escalation":
        ticket_id = payload.get("ticket_id", "UNKNOWN")
        return (
            f"✓ Escalation created for ticket {ticket_id}. "
            "The on-call team has been notified. [MOCK]"
        )
    if action_type == "update_ticket":
        ticket_id = payload.get("ticket_id", "UNKNOWN")
        return f"✓ Ticket {ticket_id} updated. [MOCK]"
    if action_type == "create_followup_task":
        return "✓ Follow-up task created and assigned. [MOCK]"
    return f"✓ Action {action_type!r} executed. [MOCK]"
