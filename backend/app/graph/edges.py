"""
app/graph/edges.py
───────────────────
Conditional routing logic for the LangGraph state machine.
All routing decisions are deterministic Python — no LLM involved.
"""

from __future__ import annotations

from app.graph.state import AgentState


def route_after_classify(state: AgentState) -> str:
    """
    After classify_and_route, decide which tool node to call first.
    If both are needed, start with document retrieval (docs provide policy context
    that helps interpret structured data results).
    """
    needs_docs = state.get("needs_documents", False)
    needs_data = state.get("needs_structured_data", False)

    if needs_docs and needs_data:
        return "retrieve_docs"   # retrieve_docs → rank_precedence → lookup_data
    if needs_docs:
        return "retrieve_docs"
    if needs_data:
        return "lookup_data"
    # Direct answer (e.g. general policy question with no account-specific data)
    return "retrieve_docs"


def route_after_retrieve(state: AgentState) -> str:
    """After retrieve_docs + rank_precedence, decide whether to also look up data."""
    if state.get("needs_structured_data", False):
        return "lookup_data"
    return "draft_answer"


def route_after_draft(state: AgentState) -> str:
    """
    After draft_answer:
    - If escalation is needed (confidence != high OR force_escalate), go to propose_action
    - Otherwise END
    """
    response = state.get("final_response", {})
    escalate = response.get("escalate", False) if response else False
    force = state.get("force_escalate", False)

    if escalate or force:
        return "propose_action"
    return "__end__"


def route_retry_or_escalate(state: AgentState) -> str:
    """
    After a tool validation error: retry up to 2 times, then escalate.
    """
    retry_count = state.get("retry_count", 0)
    if retry_count < 2:
        return "classify_and_route"
    return "draft_answer"  # will produce low-confidence → escalation
