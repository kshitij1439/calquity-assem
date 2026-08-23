"""
app/tools/document_search.py
──────────────────────────────
Tool 1: search_documents

Searches the Qdrant vector store for relevant document chunks.
Applies precedence rules IN CODE (not prompt-only):
  - Deprecated docs excluded by default
  - Results sorted by precedence_tier ASC (contract first)
  - Contract chunks with matching account_scope labeled [OVERRIDES DEFAULT POLICY]
  - Tier-4 chunks labeled [HISTORICAL — MAY BE INCORRECT, NOT A POLICY SOURCE]
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.retrieval.qdrant_client import get_qdrant_client

settings = get_settings()


class DocumentSearchInput(BaseModel):
    query: str = Field(description="Natural-language search query")
    doc_type_filter: (
        Literal["policy", "sop", "product_doc", "contract", "ticket_history"] | None
    ) = Field(default=None, description="Restrict to a specific document type")
    account_id: str | None = Field(
        default=None,
        description="Active account ID (e.g. ACCT-001). Enables contract-level results.",
    )
    include_deprecated: bool = Field(
        default=False,
        description="Set True only when user explicitly asks about old/historical policy.",
    )
    top_k: int = Field(default=6, ge=1, le=20)


class RankedChunk(BaseModel):
    doc_id: str
    text: str
    source_file: str
    doc_type: str
    status: str
    precedence_tier: int
    account_scope: str | None
    score: float
    display_text: str  # text with precedence label injected


def _apply_labels(chunk: dict[str, Any], active_account_id: str | None) -> str:
    """Inject display labels based on precedence tier and account scope."""
    text = chunk["text"]
    tier = chunk.get("precedence_tier", 99)
    scope = chunk.get("account_scope")

    if tier == 1 and scope and scope == active_account_id:
        return f"[OVERRIDES DEFAULT POLICY — {chunk['source_file']}]\n{text}"
    if tier == 4:
        return (
            f"[HISTORICAL — MAY BE INCORRECT, NOT A POLICY SOURCE "
            f"({chunk['source_file']})]\n{text}"
        )
    return text


def _filter_by_account_scope(
    results: list[dict[str, Any]], account_id: str | None
) -> list[dict[str, Any]]:
    """
    Exclude contract documents scoped to OTHER accounts.
    General docs (account_scope=None) are always included.
    """
    filtered = []
    for r in results:
        scope = r.get("account_scope")
        if scope is None:
            filtered.append(r)
        elif scope == account_id:
            filtered.append(r)
        # else: skip — this is another account's contract
    return filtered


@tool(args_schema=DocumentSearchInput)
def search_documents(
    query: str,
    doc_type_filter: str | None = None,
    account_id: str | None = None,
    include_deprecated: bool = False,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """
    Search ParcelPilot's knowledge base (policies, SOPs, product docs,
    customer contracts, and historical tickets) for relevant information.

    Returns chunks ranked by relevance and sorted by document precedence tier.
    Contract chunks for the active account are labeled [OVERRIDES DEFAULT POLICY].
    """
    client = get_qdrant_client()

    # Build Qdrant filter
    must_conditions = []

    if not include_deprecated:
        must_conditions.append(
            {"key": "status", "match": {"value": "current"}}
        )

    if doc_type_filter:
        must_conditions.append(
            {"key": "doc_type", "match": {"value": doc_type_filter}}
        )

    qdrant_filter = {"must": must_conditions} if must_conditions else None

    # Get embedder and embed query
    from app.retrieval.ingest import _get_embedder
    embedder = _get_embedder()
    query_vector = embedder.embed_query(query)

    # Search Qdrant
    try:
        search_results = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k * 2,  # over-fetch to allow post-filter
            with_payload=True,
            score_threshold=0.3,
        )
    except Exception:
        # Fallback if payload index is missing on Qdrant Cloud
        search_results = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            limit=top_k * 3,
            with_payload=True,
            score_threshold=0.3,
        )

    # Post-filter: status + doc_type + remove other accounts' contract docs
    raw = []
    for r in search_results:
        if not r.payload:
            continue
        p = r.payload
        if not include_deprecated and p.get("status") != "current":
            continue
        if doc_type_filter and p.get("doc_type") != doc_type_filter:
            continue
        raw.append({**p, "score": r.score, "qdrant_id": str(r.id)})
    filtered = _filter_by_account_scope(raw, account_id)

    # Sort by precedence_tier ASC (contract first = tier 1, ticket last = tier 4)
    sorted_chunks = sorted(filtered, key=lambda x: x.get("precedence_tier", 99))

    # Trim to top_k and inject display labels
    output = []
    for chunk in sorted_chunks[:top_k]:
        display = _apply_labels(chunk, account_id)
        output.append(
            {
                "doc_id": chunk.get("doc_id", ""),
                "text": chunk.get("text", ""),
                "display_text": display,
                "source_file": chunk.get("source_file", ""),
                "doc_type": chunk.get("doc_type", ""),
                "status": chunk.get("status", ""),
                "precedence_tier": chunk.get("precedence_tier", 99),
                "account_scope": chunk.get("account_scope"),
                "score": chunk.get("score", 0.0),
            }
        )

    return output
