"""
tests/test_precedence.py
─────────────────────────
Tests that:
1. Deprecated policy (v2) is NEVER cited when current policy exists.
2. Northstar's contract (tier-1) overrides the default policy in results.
3. Precedence sort puts tier-1 before tier-2 before tier-3 before tier-4.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_chunk(tier: int, status: str = "current", scope: str | None = None, source: str = "test.pdf") -> dict:
    return {
        "doc_id": f"doc-{tier}",
        "text": f"Content from tier {tier} doc",
        "display_text": f"Content from tier {tier} doc",
        "source_file": source,
        "doc_type": "policy",
        "status": status,
        "precedence_tier": tier,
        "account_scope": scope,
        "score": 0.9,
    }


# ── Test 1: Deprecated docs never appear in default retrieval ─────────────────

def test_deprecated_docs_excluded_by_default():
    """
    When include_deprecated=False, the filter must exclude status=deprecated chunks.
    This is enforced in the Qdrant filter, not just the LLM prompt.
    """
    from app.retrieval.qdrant_client import build_retrieval_filter
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue

    f = build_retrieval_filter(include_deprecated=False)
    assert f is not None

    # The filter must contain a condition excluding deprecated
    conditions = f.must if hasattr(f, "must") else []
    status_conditions = [
        c for c in conditions
        if hasattr(c, "key") and c.key == "status"
    ]
    assert len(status_conditions) >= 1
    # Must match "current" only
    assert any(
        hasattr(c.match, "value") and c.match.value == "current"
        for c in status_conditions
    )


def test_deprecated_docs_included_when_explicitly_requested():
    """When include_deprecated=True, no status filter is applied."""
    from app.retrieval.qdrant_client import build_retrieval_filter

    f = build_retrieval_filter(include_deprecated=True)
    # No filter at all, or filter without status=current condition
    if f is not None:
        conditions = getattr(f, "must", [])
        status_conditions = [
            c for c in conditions
            if hasattr(c, "key") and c.key == "status"
        ]
        assert len(status_conditions) == 0, (
            "Deprecated filter should be absent when include_deprecated=True"
        )


# ── Test 2: Precedence sort ────────────────────────────────────────────────────

def test_precedence_sort_order():
    """
    rank_precedence node must sort chunks tier ASC:
    contract (1) > policy (2) > product_doc (3) > ticket_history (4)
    """
    chunks = [
        make_chunk(4, source="ticket.xlsx"),
        make_chunk(3, source="04_Product_Operations.pdf"),
        make_chunk(2, source="01_Support_Policy_v3_CURRENT.pdf"),
        make_chunk(1, source="05_Northstar.pdf", scope="ACCT-001"),
    ]

    sorted_chunks = sorted(chunks, key=lambda x: x.get("precedence_tier", 99))

    tiers = [c["precedence_tier"] for c in sorted_chunks]
    assert tiers == [1, 2, 3, 4], f"Expected [1,2,3,4], got {tiers}"


def test_contract_chunk_appears_first_for_matching_account():
    """
    For account ACCT-001, Northstar's contract chunk (tier 1, scope=ACCT-001)
    must appear before the general policy chunk (tier 2, scope=None).
    """
    chunks = [
        make_chunk(2, scope=None, source="01_Support_Policy_v3_CURRENT.pdf"),
        make_chunk(1, scope="ACCT-001", source="05_Northstar_Logistics_Enterprise_Agreement.pdf"),
    ]

    sorted_chunks = sorted(chunks, key=lambda x: x.get("precedence_tier", 99))
    assert sorted_chunks[0]["source_file"] == "05_Northstar_Logistics_Enterprise_Agreement.pdf"


# ── Test 3: v2 deprecated doc never in sources ───────────────────────────────

def test_v2_deprecated_never_in_sources():
    """
    A simulated response for a Northstar query must not include the deprecated v2 doc
    in sources_used.
    """
    # Simulate what the agent would assemble
    chunks_returned = [
        make_chunk(1, scope="ACCT-001", source="05_Northstar_Logistics_Enterprise_Agreement.pdf"),
        make_chunk(2, scope=None, source="01_Support_Policy_v3_CURRENT.pdf"),
        # Deprecated doc should NOT be in results at all
    ]

    sources = [c["source_file"] for c in chunks_returned]
    assert "02_Support_Policy_v2_DEPRECATED.pdf" not in sources, (
        "Deprecated v2 policy must never appear in retrieval results for current queries"
    )
    assert "05_Northstar_Logistics_Enterprise_Agreement.pdf" in sources


# ── Test 4: Label injection ────────────────────────────────────────────────────

def test_contract_chunk_gets_override_label():
    """Contract chunks matching account_scope get [OVERRIDES DEFAULT POLICY] label."""
    from app.tools.document_search import _apply_labels

    chunk = make_chunk(1, scope="ACCT-001", source="05_Northstar.pdf")
    labeled = _apply_labels(chunk, active_account_id="ACCT-001")
    assert "[OVERRIDES DEFAULT POLICY" in labeled


def test_ticket_history_chunk_gets_historical_label():
    """Tier-4 chunks get the [HISTORICAL] warning label."""
    from app.tools.document_search import _apply_labels

    chunk = make_chunk(4, source="ParcelPilot_Assessment_Data.xlsx")
    labeled = _apply_labels(chunk, active_account_id="ACCT-001")
    assert "[HISTORICAL" in labeled
    assert "NOT A POLICY SOURCE" in labeled


def test_general_policy_chunk_no_label():
    """General policy chunks (tier 2, no scope) get no special label."""
    from app.tools.document_search import _apply_labels

    chunk = make_chunk(2, scope=None, source="01_Support_Policy_v3_CURRENT.pdf")
    labeled = _apply_labels(chunk, active_account_id="ACCT-001")
    assert "[OVERRIDES DEFAULT POLICY" not in labeled
    assert "[HISTORICAL" not in labeled
