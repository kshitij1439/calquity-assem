"""
app/graph/state.py
───────────────────
LangGraph state schema (TypedDict).
All nodes read/write this shared state object.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class AgentResponse(BaseModel):
    answer: str
    sources_used: list[str] = Field(default_factory=list, description="List of source document names used in answer")
    confidence: Literal["high", "medium", "low"]
    escalate: bool
    escalation_reason: str | None = None


class AgentState(TypedDict):
    # Message history (LangGraph managed)
    messages: Annotated[list[BaseMessage], add_messages]

    # Auth context (injected at entry, never modified by nodes)
    account_id: str
    user_role: str  # "staff" | "customer"

    # Retrieved context
    retrieved_docs: list[dict[str, Any]]
    structured_data: dict[str, Any] | None

    # Tool execution trace (shown in frontend badge)
    tool_trace: list[str]

    # Retry counter for malformed tool calls
    retry_count: int

    # Routing intent from classify_and_route node
    needs_documents: bool
    needs_structured_data: bool
    include_deprecated_docs: bool

    # Action proposal (set by propose_action node)
    pending_action: dict[str, Any] | None

    # Final structured response
    final_response: dict[str, Any] | None

    # Escalation flag (set in code, not just prompt)
    force_escalate: bool
    escalation_reason: str | None
