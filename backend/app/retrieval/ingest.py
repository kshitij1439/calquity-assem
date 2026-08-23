"""
app/retrieval/ingest.py
────────────────────────
Document ingestion pipeline.

Steps:
1. Load PDF → extract text (pypdf)
2. Chunk text (RecursiveCharacterTextSplitter)
3. Attach precedence metadata (at ingestion time, not LLM-time)
4. Embed with a sentence-transformers-compatible model
5. Upsert to Qdrant

Also handles Excel ticket history → text chunks → tier-4 metadata.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from qdrant_client.http.models import PointStruct

from app.config import get_settings
from app.retrieval.qdrant_client import ensure_collection, get_qdrant_client

settings = get_settings()

# ── Document metadata catalogue ───────────────────────────────────────────────
# Maps filename stem → fixed metadata. These are facts, not LLM inferences.

DOCUMENT_CATALOGUE: dict[str, dict[str, Any]] = {
    "01_Support_Policy_v3_CURRENT": {
        "doc_type": "policy",
        "status": "current",
        "effective_date": "2026-05-01",
        "account_scope": None,
        "precedence_tier": 2,
    },
    "02_Support_Policy_v2_DEPRECATED": {
        "doc_type": "policy",
        "status": "deprecated",
        "effective_date": "2025-01-01",
        "account_scope": None,
        "precedence_tier": 2,
    },
    "03_Cancellation_and_Service_Credit_SOP_v4": {
        "doc_type": "sop",
        "status": "current",
        "effective_date": "2026-06-15",
        "account_scope": None,
        "precedence_tier": 2,
    },
    "04_Product_Operations_Guide_and_Known_Issues": {
        "doc_type": "product_doc",
        "status": "current",
        "effective_date": "2026-08-14",
        "account_scope": None,
        "precedence_tier": 3,
    },
    "05_Northstar_Logistics_Enterprise_Agreement": {
        "doc_type": "contract",
        "status": "current",
        "effective_date": "2026-01-01",
        "account_scope": "ACCT-001",
        "precedence_tier": 1,
    },
    "06_LumenWorks_Service_Agreement": {
        "doc_type": "contract",
        "status": "current",
        "effective_date": "2026-03-01",
        "account_scope": "ACCT-002",
        "precedence_tier": 1,
    },
}


def _make_doc_id(source_file: str, chunk_index: int) -> str:
    """Deterministic UUID from filename + chunk index for idempotent upserts."""
    raw = f"{source_file}::chunk::{chunk_index}"
    return str(uuid.UUID(hashlib.md5(raw.encode()).hexdigest()))


def _get_embedder():
    """
    Return an embedding function compatible with the configured vector size.
    Uses langchain-community's HuggingFace embeddings (runs locally, no API key).
    Falls back to Groq/OpenAI embedding if GROQ_API_KEY is set.
    """
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )
    except Exception:
        raise RuntimeError(
            "Could not load embedding model. "
            "Run: pip install sentence-transformers"
        )


def ingest_pdf(pdf_path: Path, embedder=None) -> int:
    """
    Ingest a single PDF into Qdrant.
    Returns the number of chunks upserted.
    """
    stem = pdf_path.stem
    if stem not in DOCUMENT_CATALOGUE:
        raise ValueError(
            f"No metadata entry for {stem!r}. "
            "Add it to DOCUMENT_CATALOGUE before ingesting."
        )

    meta = DOCUMENT_CATALOGUE[stem]
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    client = get_qdrant_client()
    ensure_collection(client)
    emb = embedder or _get_embedder()

    points = []
    for i, chunk in enumerate(chunks):
        doc_id = _make_doc_id(pdf_path.name, i)
        vector = emb.embed_query(chunk.page_content)
        payload = {
            "text": chunk.page_content,
            "source_file": pdf_path.name,
            "chunk_index": i,
            "doc_id": doc_id,
            **meta,
        }
        points.append(PointStruct(id=doc_id, vector=vector, payload=payload))

    # Upsert in batches of 64
    batch_size = 64
    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[i : i + batch_size],
        )

    print(f"  ✓ {pdf_path.name}: {len(chunks)} chunks upserted")
    return len(chunks)


def ingest_ticket_history(tickets: list[dict[str, Any]], embedder=None) -> int:
    """
    Convert ticket records to text chunks and ingest as tier-4 context docs.
    Each ticket becomes one chunk.
    """
    client = get_qdrant_client()
    ensure_collection(client)
    emb = embedder or _get_embedder()

    points = []
    for ticket in tickets:
        ticket_id = ticket.get("id", "UNKNOWN")
        account_id = ticket.get("account_id", None)
        text = (
            f"Ticket {ticket_id} | Account: {account_id} | "
            f"Severity: {ticket.get('severity')} | Status: {ticket.get('status')}\n"
            f"Subject: {ticket.get('subject', '')}\n"
            f"Description: {ticket.get('description', '')}\n"
            f"Resolution: {ticket.get('resolution_notes', '')}"
        )
        doc_id = _make_doc_id(f"ticket_history::{ticket_id}", 0)
        vector = emb.embed_query(text)
        payload = {
            "text": text,
            "source_file": "ParcelPilot_Assessment_Data.xlsx",
            "doc_id": doc_id,
            "doc_type": "ticket_history",
            "status": "current",
            "effective_date": "2026-08-16",
            "account_scope": account_id,
            "precedence_tier": 4,
            "ticket_id": ticket_id,
        }
        points.append(PointStruct(id=doc_id, vector=vector, payload=payload))

    batch_size = 64
    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[i : i + batch_size],
        )

    print(f"  ✓ Ticket history: {len(points)} chunks upserted")
    return len(points)
