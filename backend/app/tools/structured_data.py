"""
app/tools/structured_data.py
──────────────────────────────
Tool 2: query_operational_data

Structured data lookup over Postgres via the repository layer.
The LLM NEVER writes SQL. It calls this tool with a typed intent + params.
Access control is enforced inside repository functions, not here.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.data.database import get_db
from app.data.repository import (
    AccessDenied,
    check_cancellation_eligibility,
    check_sla,
    get_account,
    get_order,
    list_orders,
    list_tickets,
)


class OperationalDataInput(BaseModel):
    intent: Literal[
        "get_order",
        "get_account",
        "check_sla",
        "list_tickets",
        "list_orders",
        "check_cancellation_eligibility",
    ] = Field(description="What data operation to perform")
    params: dict[str, Any] = Field(
        description=(
            "Intent-specific parameters. "
            "get_order: {order_id}. "
            "get_account: {account_id}. "
            "check_sla: {ticket_id}. "
            "list_tickets: {severity?, status?, known_issue_ref?, limit?}. "
            "list_orders: {status?, limit?}. "
            "check_cancellation_eligibility: {order_id}."
        )
    )
    requester_account_id: str = Field(
        description=(
            "The active account ID of the requester. "
            "Use '*' only for internal staff. "
            "This is set by the auth layer, not the user."
        )
    )


def _serialize(obj: Any) -> Any:
    """Convert dataclasses/models to JSON-serialisable dicts."""
    if isinstance(obj, AccessDenied):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        # SQLAlchemy model — extract mapped columns
        return {
            k: v for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


@tool(args_schema=OperationalDataInput)
def query_operational_data(
    intent: str,
    params: dict[str, Any],
    requester_account_id: str,
) -> dict[str, Any]:
    """
    Query ParcelPilot's operational database.
    Access is strictly scoped to the requester's account.
    Returns structured data or an access_denied error if cross-account access is attempted.
    """
    with get_db() as db:
        result: Any

        if intent == "get_order":
            order_id = params.get("order_id", "")
            result = get_order(order_id, requester_account_id, db)

        elif intent == "get_account":
            account_id = params.get("account_id", requester_account_id)
            result = get_account(account_id, requester_account_id, db)

        elif intent == "check_sla":
            ticket_id = params.get("ticket_id", "")
            result = check_sla(ticket_id, requester_account_id, db)

        elif intent == "list_tickets":
            result = list_tickets(
                requesting_account_id=requester_account_id,
                db=db,
                severity=params.get("severity"),
                status=params.get("status"),
                known_issue_ref=params.get("known_issue_ref"),
                limit=params.get("limit", 50),
            )

        elif intent == "list_orders":
            result = list_orders(
                requesting_account_id=requester_account_id,
                db=db,
                status=params.get("status"),
                limit=params.get("limit", 50),
            )

        elif intent == "check_cancellation_eligibility":
            order_id = params.get("order_id", "")
            result = check_cancellation_eligibility(order_id, requester_account_id, db)

        else:
            return {
                "error": "unknown_intent",
                "detail": f"Intent {intent!r} is not supported.",
                "supported_intents": [
                    "get_order", "get_account", "check_sla",
                    "list_tickets", "list_orders",
                    "check_cancellation_eligibility",
                ],
            }

        return {"intent": intent, "result": _serialize(result)}
