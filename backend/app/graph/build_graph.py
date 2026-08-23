"""
app/graph/build_graph.py
─────────────────────────
Assembles the LangGraph StateGraph.

Checkpointer: MemorySaver (in-memory) for local dev / assessment.
Production path: Postgres-backed checkpointer (noted in architecture-note.md).

Two entry points:
  - Default: full chat flow (classify → retrieve → lookup → draft → propose)
  - "execute": confirmation entry point (skips to execute_action_node)
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.graph.edges import route_after_classify, route_after_draft, route_after_retrieve
from app.graph.nodes import (
    classify_and_route,
    draft_answer,
    execute_action_node,
    lookup_data,
    propose_action_node,
    rank_precedence,
    retrieve_docs,
)
from app.graph.state import AgentState


def build_graph():
    """Build and compile the ParcelPilot support agent graph."""
    builder = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    builder.add_node("classify_and_route", classify_and_route)
    builder.add_node("retrieve_docs", retrieve_docs)
    builder.add_node("rank_precedence", rank_precedence)
    builder.add_node("lookup_data", lookup_data)
    builder.add_node("draft_answer", draft_answer)
    builder.add_node("propose_action", propose_action_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.set_entry_point("classify_and_route")

    # ── Edges ─────────────────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "classify_and_route",
        route_after_classify,
        {
            "retrieve_docs": "retrieve_docs",
            "lookup_data": "lookup_data",
            "draft_answer": "draft_answer",
        },
    )

    # retrieve_docs → rank_precedence (always)
    builder.add_edge("retrieve_docs", "rank_precedence")

    # rank_precedence → lookup_data or draft_answer
    builder.add_conditional_edges(
        "rank_precedence",
        route_after_retrieve,
        {
            "lookup_data": "lookup_data",
            "draft_answer": "draft_answer",
        },
    )

    # lookup_data → draft_answer (always)
    builder.add_edge("lookup_data", "draft_answer")

    # draft_answer → propose_action or END
    builder.add_conditional_edges(
        "draft_answer",
        route_after_draft,
        {
            "propose_action": "propose_action",
            "__end__": END,
        },
    )

    # propose_action → END (propose_action_node handles interrupt dynamically)
    builder.add_edge("propose_action", END)

    # ── Compile with checkpointer ─────────────────────────────────────────────
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    return graph


# Singleton
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
