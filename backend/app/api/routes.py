"""
app/api/routes.py
──────────────────
FastAPI API routes:
  POST /chat              → invoke LangGraph agent
  POST /confirm-action    → submit confirmation token → execute action
  GET  /dashboard         → proactive issue detection data
  GET  /health            → liveness check
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.context import UserContext, get_user_context
from app.data.database import get_db_session
from app.graph.build_graph import get_graph
from app.tools.actions import execute_action

log = structlog.get_logger()
router = APIRouter()


# ── Request / Response schemas ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, description="Session thread ID for memory")


class ChatResponse(BaseModel):
    turn_id: str
    thread_id: str
    answer: str
    sources_used: list[str]
    confidence: str
    escalate: bool
    escalation_reason: str | None
    tool_trace: list[str]
    pending_action: dict[str, Any] | None
    latency_ms: int


class ConfirmActionRequest(BaseModel):
    confirmation_token: str


class ConfirmActionResponse(BaseModel):
    success: bool
    message: str
    action_type: str | None = None
    executed_at: str | None = None


class DashboardResponse(BaseModel):
    sla_breaches: list[dict[str, Any]]
    issue_clusters: list[dict[str, Any]]
    cross_customer_spikes: list[dict[str, Any]]
    snapshot_time: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "snapshot_time": "2026-08-16T11:00:00+05:30"}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    ctx: UserContext = Depends(get_user_context),
):
    """
    Main chat endpoint. Invokes the LangGraph agent with the user message.
    Returns the structured response including tool trace.
    """
    turn_id = str(uuid.uuid4())
    thread_id = request.thread_id or str(uuid.uuid4())

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "account_id": ctx.account_id,
        "user_role": ctx.role,
        "retrieved_docs": [],
        "structured_data": None,
        "tool_trace": [],
        "retry_count": 0,
        "needs_documents": False,
        "needs_structured_data": False,
        "include_deprecated_docs": False,
        "pending_action": None,
        "final_response": None,
        "force_escalate": False,
        "escalation_reason": None,
    }

    t0 = time.time()
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: graph.invoke(initial_state, config=config)
        )
    except Exception as e:
        log.error("api.chat.error", turn_id=turn_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {e}",
        )

    latency = int((time.time() - t0) * 1000)
    final = result.get("final_response") or {}

    log.info(
        "api.chat.complete",
        turn_id=turn_id,
        account_id=ctx.account_id,
        tools_called=result.get("tool_trace", []),
        latency_ms=latency,
        sources=final.get("sources_used", []),
        confidence=final.get("confidence", "unknown"),
        escalated=final.get("escalate", False),
    )

    return ChatResponse(
        turn_id=turn_id,
        thread_id=thread_id,
        answer=final.get("answer", "No response generated."),
        sources_used=final.get("sources_used", []),
        confidence=final.get("confidence", "low"),
        escalate=final.get("escalate", False),
        escalation_reason=final.get("escalation_reason"),
        tool_trace=result.get("tool_trace", []),
        pending_action=result.get("pending_action"),
        latency_ms=latency,
    )


@router.post("/confirm-action", response_model=ConfirmActionResponse)
async def confirm_action(
    request: ConfirmActionRequest,
    ctx: UserContext = Depends(get_user_context),
):
    """
    Submit a confirmation token to execute a previously proposed action.
    The token must be valid and unexpired (5-min TTL).
    """
    result = execute_action.invoke({"confirmation_token": request.confirmation_token})

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("detail", "Invalid or expired confirmation token."),
        )

    log.info(
        "api.confirm_action",
        account_id=ctx.account_id,
        action_type=result.get("action_type"),
        idempotency_key=result.get("idempotency_key"),
    )

    return ConfirmActionResponse(
        success=True,
        message=result.get("message", "Action executed."),
        action_type=result.get("action_type"),
        executed_at=result.get("executed_at"),
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    ctx: UserContext = Depends(get_user_context),
    include_llm_summary: bool = False,
):
    """
    Proactive issue detection dashboard.
    Requires staff role — customers cannot access this endpoint.
    """
    if not ctx.is_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dashboard access requires staff role.",
        )

    from app.analytics.issue_detection import (
        get_issue_clusters,
        get_sla_breaches,
        get_spikes,
    )
    import dataclasses

    breaches = get_sla_breaches()
    clusters = get_issue_clusters(include_llm_summary=include_llm_summary)
    spikes = get_spikes()

    return DashboardResponse(
        sla_breaches=[dataclasses.asdict(b) for b in breaches],
        issue_clusters=[dataclasses.asdict(c) for c in clusters],
        cross_customer_spikes=[dataclasses.asdict(s) for s in spikes],
        snapshot_time="2026-08-16T11:00:00+05:30",
    )
