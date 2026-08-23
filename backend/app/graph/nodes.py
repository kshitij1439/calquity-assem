"""
app/graph/nodes.py
───────────────────
LangGraph node implementations.

Nodes:
  classify_and_route   → determines which tools are needed
  retrieve_docs        → calls document_search tool
  lookup_data          → calls query_operational_data tool
  rank_precedence      → pure Python sort (zero LLM)
  draft_answer         → LLM call → AgentResponse structured output
  propose_action_node  → wraps propose_action tool + interrupt()
  execute_action_node  → validates token + calls execute_action tool
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings, SNAPSHOT_NOW
from app.graph.state import AgentResponse, AgentState
from app.tools.document_search import search_documents
from app.tools.structured_data import query_operational_data
from app.tools.actions import propose_action, execute_action

settings = get_settings()
log = structlog.get_logger()

# ── LLM factory with circuit breaker ──────────────────────────────────────────
_groq_failure_count = 0


def _get_llm(force_fallback: bool = False):
    global _groq_failure_count
    model_name = settings.fallback_model if (force_fallback or _groq_failure_count >= settings.llm_circuit_breaker_threshold) else settings.primary_model
    if model_name.startswith("gemini"):
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.gemini_api_key,
            timeout=settings.llm_timeout_seconds,
        )
    return ChatGroq(
        model=model_name,
        api_key=settings.groq_api_key,
        timeout=settings.llm_timeout_seconds,
    )


def _call_llm_with_fallback(messages, structured_output_class=None):
    """Call LLM with automatic fallback and PydanticOutputParser recovery."""
    global _groq_failure_count
    llm = _get_llm()
    if structured_output_class:
        try:
            return llm.with_structured_output(structured_output_class).invoke(messages)
        except Exception as e:
            log.warning("llm.structured_output_retry_with_parser", error=str(e))
            from langchain_core.output_parsers import PydanticOutputParser
            parser = PydanticOutputParser(pydantic_object=structured_output_class)
            formatted_messages = list(messages) + [HumanMessage(content=f"\n{parser.get_format_instructions()}")]
            try:
                raw = llm.invoke(formatted_messages)
                return parser.parse(raw.content)
            except Exception as inner_e:
                _groq_failure_count += 1
                log.error("llm.failure_switching_fallback", error=str(inner_e))
                fallback_llm = _get_llm(force_fallback=True)
                raw = fallback_llm.invoke(formatted_messages)
                return parser.parse(raw.content)
    return llm.invoke(messages)


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are ParcelPilot's internal support agent. You help authorised 
support staff investigate customer issues, answer support questions, and work with 
operational data.

IMPORTANT RULES:
1. Only use information from retrieved documents and structured data — never hallucinate.
2. When sources conflict, defer to the precedence order: contract > current policy/SOP > product docs > ticket history.
3. Ticket history is CONTEXT ONLY and may be incorrect. Never cite it as authoritative.
4. If a customer contract overrides the default policy, state this explicitly.
5. Never promise a credit or cancellation outcome when key facts are unknown.
6. The current snapshot time is {SNAPSHOT_NOW.isoformat()} (frozen dataset reference).
7. When confidence is not high, recommend escalation with a clear reason.
"""


# ── Node 1: classify_and_route ─────────────────────────────────────────────────

def classify_and_route(state: AgentState) -> dict[str, Any]:
    """
    Analyse the latest user message and determine which tools are needed.
    Uses a lightweight LLM call with structured output.
    """
    from pydantic import BaseModel as PydanticBase

    class RouteDecision(PydanticBase):
        needs_documents: bool
        needs_structured_data: bool
        include_deprecated_docs: bool
        reasoning: str

    last_message = state["messages"][-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)

    messages = [
        SystemMessage(content=(
            "You are a routing classifier. Analyse the query and decide which tools are needed.\n"
            "needs_documents: True if the query requires policy, SOP, contract, or product doc information.\n"
            "needs_structured_data: True if the query requires account, order, or ticket data.\n"
            "include_deprecated_docs: True ONLY if the user explicitly asks about old/historical/deprecated policy.\n"
        )),
        HumanMessage(content=f"Query: {query}"),
    ]

    decision = _call_llm_with_fallback(messages, RouteDecision)

    log.info("node.classify", needs_docs=decision.needs_documents,
             needs_data=decision.needs_structured_data,
             reasoning=decision.reasoning)

    return {
        "needs_documents": decision.needs_documents,
        "needs_structured_data": decision.needs_structured_data,
        "include_deprecated_docs": decision.include_deprecated_docs,
        "tool_trace": state.get("tool_trace", []),
        "retry_count": state.get("retry_count", 0),
    }


# ── Node 2: retrieve_docs ──────────────────────────────────────────────────────

def retrieve_docs(state: AgentState) -> dict[str, Any]:
    """Call the document_search tool and store results in state."""
    last_message = state["messages"][-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)

    t0 = time.time()
    try:
        results = search_documents.invoke({
            "query": query,
            "account_id": state["account_id"],
            "include_deprecated": state.get("include_deprecated_docs", False),
            "top_k": 6,
        })
        latency = int((time.time() - t0) * 1000)
        log.info("node.retrieve_docs", chunks=len(results), latency_ms=latency)
        trace = state.get("tool_trace", []) + ["document_search"]
        return {"retrieved_docs": results, "tool_trace": trace}

    except Exception as e:
        log.error("node.retrieve_docs.error", error=str(e))
        # Graceful degradation: continue with empty docs
        return {
            "retrieved_docs": [],
            "tool_trace": state.get("tool_trace", []) + ["document_search(failed)"],
        }


# ── Node 3: lookup_data ────────────────────────────────────────────────────────

def lookup_data(state: AgentState) -> dict[str, Any]:
    """
    Use the LLM to determine the correct intent + params for the query,
    then call query_operational_data.
    """
    from pydantic import BaseModel as PydanticBase

    class DataIntent(PydanticBase):
        intent: str
        params: dict[str, Any]

    last_message = state["messages"][-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)

    # Ask LLM to extract structured intent
    intent_messages = [
        SystemMessage(content=(
            "Extract a structured data lookup intent from the query. "
            "Supported intents: get_order, get_account, check_sla, list_tickets, "
            "list_orders, check_cancellation_eligibility. "
            "Return the intent name and params dict. "
            "If multiple lookups are needed, pick the most important one."
        )),
        HumanMessage(content=f"Query: {query}"),
    ]

    effective_account = "*" if state["user_role"] == "staff" else state["account_id"]

    t0 = time.time()
    try:
        intent_decision = _call_llm_with_fallback(intent_messages, DataIntent)
        result = query_operational_data.invoke({
            "intent": intent_decision.intent,
            "params": intent_decision.params,
            "requester_account_id": effective_account,
        })
        latency = int((time.time() - t0) * 1000)

        # Detect access denied
        force_escalate = False
        escalation_reason = None
        if isinstance(result, dict) and result.get("result", {}).get("error") == "access_denied":
            force_escalate = True
            escalation_reason = "Cross-account data access attempted — escalation required."

        log.info("node.lookup_data", intent=intent_decision.intent,
                 latency_ms=latency, access_denied=force_escalate)

        trace = state.get("tool_trace", []) + ["query_operational_data"]
        return {
            "structured_data": result,
            "tool_trace": trace,
            "force_escalate": force_escalate,
            "escalation_reason": escalation_reason,
        }

    except Exception as e:
        log.error("node.lookup_data.error", error=str(e))
        return {
            "structured_data": {"error": str(e)},
            "tool_trace": state.get("tool_trace", []) + ["query_operational_data(failed)"],
        }


# ── Node 4: rank_precedence ────────────────────────────────────────────────────

def rank_precedence(state: AgentState) -> dict[str, Any]:
    """
    Pure Python deterministic sort — zero LLM involvement.
    Already done inside search_documents, but this node re-asserts
    and logs the final order for auditability.
    """
    docs = state.get("retrieved_docs", [])
    sorted_docs = sorted(docs, key=lambda x: x.get("precedence_tier", 99))
    trace = state.get("tool_trace", []) + ["rank_precedence"]
    log.info("node.rank_precedence", doc_count=len(sorted_docs),
             tiers=[d.get("precedence_tier") for d in sorted_docs])
    return {"retrieved_docs": sorted_docs, "tool_trace": trace}


# ── Node 5: draft_answer ───────────────────────────────────────────────────────

def draft_answer(state: AgentState) -> dict[str, Any]:
    """
    Main LLM call. Produces a structured AgentResponse.
    Forces escalation in code (not just prompt) when:
    - confidence != "high"
    - structured_data contains required_facts with None values
    - force_escalate flag is already set
    """
    last_message = state["messages"][-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)

    # Build context from retrieved docs
    doc_context = ""
    sources: list[str] = []
    for doc in state.get("retrieved_docs", []):
        doc_context += f"\n---\n{doc.get('display_text', doc.get('text', ''))}\n"
        sources.append(doc.get("source_file", "unknown"))

    # Build context from structured data
    data_context = ""
    if state.get("structured_data"):
        data_context = f"\nStructured data:\n{json.dumps(state['structured_data'], indent=2, default=str)}\n"

    context = doc_context + data_context

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"User query: {query}\n\n"
            f"Available context:\n{context}\n\n"
            "Produce a structured answer. If you are not confident or if key facts are "
            "missing/unknown, set confidence to 'low' or 'medium' and escalate=True."
        )),
    ]

    t0 = time.time()
    try:
        response: AgentResponse = _call_llm_with_fallback(messages, AgentResponse)
    except Exception as e:
        log.error("node.draft_answer.error", error=str(e))
        response = AgentResponse(
            answer="I encountered an error generating a response. Please escalate to a human agent.",
            sources_used=[],
            confidence="low",
            escalate=True,
            escalation_reason=f"LLM error: {e}",
        )

    latency = int((time.time() - t0) * 1000)

    # ── Forced escalation (code-level rules, not prompt-only) ─────────────────
    if state.get("force_escalate"):
        response.escalate = True
        response.escalation_reason = state.get("escalation_reason") or response.escalation_reason

    if response.confidence != "high":
        response.escalate = True
        if not response.escalation_reason:
            response.escalation_reason = f"Confidence level is {response.confidence!r} — human review recommended."

    # Check for unknown required facts in structured data
    if state.get("structured_data"):
        result = state["structured_data"].get("result", {})
        if isinstance(result, dict):
            unknown_fields = [k for k, v in result.items() if v is None and k in (
                "carrier_fault", "pickup_window_end", "picked_up_at"
            )]
            if unknown_fields:
                response.escalate = True
                response.escalation_reason = (
                    f"Required facts are unknown: {unknown_fields}. "
                    "Cannot determine eligibility without verification."
                )

    log.info(
        "node.draft_answer",
        confidence=response.confidence,
        escalate=response.escalate,
        sources=response.sources_used,
        latency_ms=latency,
    )

    trace = state.get("tool_trace", []) + ["draft_answer"]
    return {
        "final_response": response.model_dump(),
        "tool_trace": trace,
        "messages": [AIMessage(content=response.answer)],
    }


# ── Node 6: propose_action_node ───────────────────────────────────────────────

def propose_action_node(state: AgentState) -> dict[str, Any]:
    """
    Determine if the draft answer implies a state change.
    If yes, call propose_action and set interrupt for user confirmation.
    """
    response = state.get("final_response", {})
    answer = response.get("answer", "")
    escalate = response.get("escalate", False)

    if not escalate:
        return {"pending_action": None}

    # Build escalation action proposal
    action_payload = {
        "ticket_id": _extract_ticket_id(answer, state),
        "reason": response.get("escalation_reason", "Low confidence response"),
        "assignee": "on-call-support-team",
        "context": answer[:500],
    }

    proposal = propose_action.invoke({
        "action_type": "create_escalation",
        "payload": action_payload,
        "account_id": state["account_id"],
    })

    # Interrupt here — execution pauses until frontend submits the token
    try:
        from langgraph.types import interrupt
        user_decision = interrupt({
            "type": "action_confirmation_required",
            "proposal": proposal,
        })
    except ImportError:
        from langgraph.errors import NodeInterrupt
        raise NodeInterrupt({
            "type": "action_confirmation_required",
            "proposal": proposal,
        })

    trace = state.get("tool_trace", []) + ["propose_action"]
    return {
        "pending_action": proposal,
        "tool_trace": trace,
    }


# ── Node 7: execute_action_node ───────────────────────────────────────────────

def execute_action_node(state: AgentState, confirmation_token: str) -> dict[str, Any]:
    """
    Separate LangGraph entry point — only called when frontend submits a valid token.
    """
    result = execute_action.invoke({"confirmation_token": confirmation_token})
    trace = state.get("tool_trace", []) + ["execute_action"]
    log.info("node.execute_action", success=result.get("success"), action=result.get("action_type"))
    return {
        "pending_action": None,
        "tool_trace": trace,
        "messages": [AIMessage(content=f"✓ Action executed: {result.get('message', '')}")]
    }


def _extract_ticket_id(text: str, state: AgentState) -> str:
    """Best-effort ticket ID extraction from context."""
    import re
    match = re.search(r"TKT-\d+", text)
    if match:
        return match.group()
    data = state.get("structured_data", {}) or {}
    result = data.get("result", {})
    if isinstance(result, dict):
        return result.get("ticket_id", result.get("id", "UNKNOWN"))
    return "UNKNOWN"
