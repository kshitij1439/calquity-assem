# ParcelPilot Support Agent — Architecture Note

## 1. Agent Design

The agent is a **LangGraph state machine** (not a manual while-loop), built as a directed graph of typed nodes that operate on a shared `AgentState` TypedDict.

### Graph flow
```
classify_and_route
     ↓
 retrieve_docs → rank_precedence ──→ lookup_data → draft_answer → propose_action
     ↓                                                  ↓
  (if only docs needed) ──────────────────────→ draft_answer
```

Each node is a pure function that receives `AgentState` and returns a partial update dict. LangGraph merges updates automatically. The `interrupt()` mechanism pauses execution at `propose_action` until the frontend submits a valid confirmation token — no polling, no setTimeout hacks.

**Checkpointer**: `MemorySaver` for local/dev. Production path is a Postgres-backed checkpointer (`PostgresSaver` from `langgraph-checkpoint-postgres`) — all thread state is already serialisable.

## 2. Tool Design

Three LangChain `@tool` functions with Pydantic input schemas:

| Tool | Purpose | Key design |
|---|---|---|
| `search_documents` | Qdrant vector search | Metadata filter excludes deprecated docs by default; precedence sort + label injection happen in Python, not the LLM prompt |
| `query_operational_data` | Postgres via typed repository | Intent dispatch pattern; LLM never writes SQL; `AccessDenied` sentinel returned on cross-account attempts |
| `propose_action` / `execute_action` | State-changing actions | JWT token with 5-min TTL + idempotency key; replayed tokens return cached result |

Malformed tool inputs produce a structured `ToolValidationError` fed back into the graph loop (max 2 retries), then fall through to `draft_answer` with low confidence → forced escalation.

## 3. Document and Structured-Data Handling

### Ingestion
- All 6 PDFs are chunked (1000 tokens, 200 overlap) using `RecursiveCharacterTextSplitter`
- Each chunk receives hard-coded metadata at ingest time (not LLM-inferred):
  - `doc_type`, `status`, `effective_date`, `account_scope`, `precedence_tier`
- Excel ticket history → text chunks → tier-4 metadata
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (runs locally, no API key)
- Upserts use deterministic MD5-based UUIDs → idempotent re-runs

### Retrieval
- Qdrant filter excludes `status: deprecated` unless user explicitly asks about historical policy
- Post-filter removes other accounts' contract docs from results
- Python sort by `precedence_tier` ASC before LLM context assembly
- Label injection: tier-1 contract chunks → `[OVERRIDES DEFAULT POLICY]`; tier-4 → `[HISTORICAL — MAY BE INCORRECT]`

### Structured data
- SQLAlchemy models: `Account`, `Order`, `Ticket`
- Every repository function takes `requesting_account_id` as a required parameter
- Cross-account access returns `AccessDenied` dataclass — not a 500, not a silent empty result
- SLA targets resolved from contract overrides first, then plan-based defaults

## 4. Source Reliability and Conflict Handling

### Precedence hierarchy (code-enforced)
```
Tier 1 (contract, account-specific) > Tier 2 (current policy/SOP) > Tier 3 (product docs) > Tier 4 (ticket history — context only)
```

The deprecated v2 policy is tagged at ingest and filtered at retrieval — it can never win over current sources in normal operation.

### Forced escalation (code, not prompt)
These conditions trigger `escalate=True` regardless of LLM output:
1. `confidence != "high"` in `AgentResponse`
2. Required facts are `null`/`None` in structured data (e.g., `carrier_fault=None`)
3. `force_escalate=True` set by `lookup_data` on `AccessDenied` result

When the agent cannot determine carrier fault status, pickup timing, or eligibility with certainty, it explicitly states the uncertainty and recommends escalation rather than guessing.

## 5. Major Trade-offs

| Decision | Choice | Alternative | Reason |
|---|---|---|---|
| Embedding model | Local `all-MiniLM-L6-v2` | OpenAI `text-embedding-3-small` | Zero API cost, runs offline, deterministic |
| Checkpointer | `MemorySaver` | Postgres-backed | Faster dev setup; swap is one line |
| Auth | Header injection | JWT from IdP | Mocked per spec; real integration is a middleware swap |
| LLM SQL | None — typed repository | LLM-generated SQL | Eliminates SQL injection and hallucinated queries entirely |
| Action execution | Mock + token gate | Real integrations | Demonstrates the contract pattern correctly; wiring real APIs is additive |
