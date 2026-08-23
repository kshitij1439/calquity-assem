"""
app/retrieval/qdrant_client.py
───────────────────────────────
Thin wrapper around the Qdrant Python client.
Provides a singleton client and collection helpers.
"""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Return a cached Qdrant client singleton."""
    if settings.qdrant_api_key:
        return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient | None = None) -> None:
    """Create the Qdrant collection and payload indexes if they do not already exist."""
    c = client or get_qdrant_client()
    existing = [col.name for col in c.get_collections().collections]
    if settings.qdrant_collection not in existing:
        c.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,
                distance=Distance.COSINE,
            ),
        )
    from qdrant_client.http.models import PayloadSchemaType
    for field_name in ["status", "doc_type", "account_id"]:
        try:
            c.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


def build_retrieval_filter(
    account_id: str | None = None,
    doc_type: str | None = None,
    include_deprecated: bool = False,
) -> Filter | None:
    """
    Build a Qdrant metadata filter for document retrieval.

    Rules (code-enforced, not prompt):
    - By default, deprecated docs are EXCLUDED.
    - If include_deprecated is True, the status filter is lifted.
    """
    conditions: list[FieldCondition] = []

    if not include_deprecated:
        conditions.append(
            FieldCondition(key="status", match=MatchValue(value="current"))
        )

    if doc_type:
        conditions.append(
            FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
        )

    if not conditions:
        return None

    return Filter(must=conditions)
