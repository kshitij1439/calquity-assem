# ParcelPilot Support Agent

Internal AI support/operations chatbot for ParcelPilot, built for the CalQuity AI Engineer assessment.

## Architecture

```
Frontend (Next.js 14 + shadcn/ui)
        ↕ HTTP (REST)
Backend (FastAPI + LangGraph)
        ↕
Qdrant (vector store) + Postgres (structured data)
```

**Agent**: LangGraph state machine → classify → retrieve docs → rank precedence → lookup data → draft answer → propose action (with interrupt for user confirmation).

## Quick Start (Docker Compose)

### Prerequisites
- Docker Desktop running
- API keys ready (Groq + Gemini)

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd parcelpilot-agent
cp backend/.env.example backend/.env
# Edit backend/.env and fill in GROQ_API_KEY and GEMINI_API_KEY
```

### 2. Start services

```bash
docker compose up --build -d
```

This starts: Postgres (5432), Qdrant (6333), Backend (8000), Frontend (3000).

### 3. Run ingestion (one-time)

```bash
# Wait for services to be healthy, then:
docker compose exec backend python scripts/ingest_data.py
```

This seeds Postgres from the Excel workbook and ingests all 6 PDFs into Qdrant.

### 4. Open the app

- Frontend: http://localhost:3000
- Chat: http://localhost:3000/chat
- Dashboard: http://localhost:3000/dashboard
- API docs: http://localhost:8000/docs

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # Fill in API keys
# Start Postgres + Qdrant via Docker:
docker run -d -p 5432:5432 -e POSTGRES_USER=parcelpilot -e POSTGRES_PASSWORD=parcelpilot -e POSTGRES_DB=parcelpilot postgres:16-alpine
docker run -d -p 6333:6333 qdrant/qdrant
# Update .env with local connection strings
python scripts/ingest_data.py
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1" > .env.local
npm run dev
```

---

## Running Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest tests/ -v --tb=short
```

Test coverage:
- `test_precedence.py` — deprecated docs excluded, precedence sort, label injection
- `test_access_control.py` — cross-account returns `AccessDenied`, staff bypass, auth headers
- `test_confirmation_gate.py` — no token / expired / valid / idempotency
- `test_eval_queries.py` — brief examples + synthetic variants, no hardcoded IDs in code

---

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key (primary LLM) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback) |
| `QDRANT_URL` | Qdrant instance URL |
| `QDRANT_API_KEY` | Qdrant cloud API key (leave blank for local) |
| `DATABASE_URL` | Async Postgres connection string |
| `SYNC_DATABASE_URL` | Sync Postgres connection string (for scripts) |
| `ACTION_TOKEN_SECRET` | Secret for signing confirmation JWT tokens |

---

## Key Design Decisions

1. **LLM never writes SQL** — all queries go through typed repository functions with mandatory `requesting_account_id` scoping.
2. **Deprecated docs filtered at retrieval** — `status: deprecated` excluded by Qdrant filter, not by LLM prompt.
3. **Precedence sort in Python** — `rank_precedence` node does a deterministic sort, zero LLM involvement.
4. **Forced escalation in code** — `confidence != "high"`, unknown required facts, or `AccessDenied` all set `escalate=True` regardless of what the LLM outputs.
5. **Confirmation gate** — `propose_action` uses LangGraph `interrupt()` and a JWT token with 5-min TTL. `execute_action` is idempotent.

---

## Stage-Wise Work Breakdown

The project was delivered systematically across 10 structured implementation stages:

### 🔹 Stage 0 — Scaffolding & Infrastructure Configuration
- Configured multi-container environment via `docker-compose.yml` (Postgres, Qdrant, FastAPI Backend, Next.js Frontend).
- Established environment variable management (`backend/app/config.py`) using `pydantic-settings`.

### 🔹 Stage 1 — Data Layer & Database Schema Design
- Defined SQLAlchemy ORM models (`Account`, `Order`, `Ticket`) in `backend/app/data/models.py`.
- Synchronized PostgreSQL Enums (`TicketStatus`, `OrderStatus`, `TicketSeverity`) to handle all assessment dataset states cleanly.
- Built `app/data/repository.py` ensuring mandatory `requesting_account_id` data isolation and `AccessDenied` protection.

### 🔹 Stage 2 — Document Retrieval & Vector Ingestion
- Integrated `qdrant_client.py` with automatic payload indexing for `status`, `doc_type`, and `account_id`.
- Implemented `scripts/ingest_data.py` to chunk PDFs and upsert vectors into Qdrant Cloud.
- Added Python-side payload filter fallbacks in `document_search.py` for maximum query resiliency.

### 🔹 Stage 3 — Operational Tools & Confirmation Gate
- Implemented `query_operational_data` and `search_documents` tools.
- Built two-phase action execution in `app/tools/actions.py` using 5-minute TTL signed JWT confirmation tokens and idempotent state handling.

### 🔹 Stage 4 — LangGraph State Machine & LLM Resiliency
- Built graph topology in `app/graph/build_graph.py` (`classify` → `retrieve` → `rank` → `lookup` → `draft` → `propose`).
- Implemented multi-provider LLM fallback router with `PydanticOutputParser` recovery for Gemini schema validation errors.
- Enforced hard precedence sorting rules (Contract overrides > Ops SOP > General FAQs > Historical tickets).

### 🔹 Stage 5 — Backend REST API & Middleware
- Built `/api/v1/chat`, `/api/v1/confirm-action`, `/api/v1/dashboard`, and `/health` routes in FastAPI.
- Added `structlog` middleware injecting `X-User-Role` and `X-Account-ID` request context into every trace.

### 🔹 Stage 6 — Analytics & Proactive Issue Detection
- Built `app/analytics/issue_detection.py` for deterministic SLA breach calculation ( urgency scoring vs snapshot time).
- Implemented known issue clustering (`KI-208`, `KI-211`) and cross-customer spike detection without LLM dependency.

### 🔹 Stage 7 — Next.js 14 Dashboard & Chat Interface
- Built modern Next.js 14 frontend using Tailwind CSS and Lucide icons.
- Implemented real-time tool trace visualization badges (`ToolTraceBadge`), modal action confirmation dialogs (`ConfirmActionDialog`), and an account context switcher (`AccountSwitcher`).

### 🔹 Stage 8 — Test Harness & Automated Verification
- Developed 35 automated pytest tests across 4 key suites (`test_access_control`, `test_confirmation_gate`, `test_eval_queries`, `test_precedence`).
- Verified 100% test pass rate and validated live HTTP response payloads for `/dashboard` and `/chat`.

### 🔹 Stage 9 — Comprehensive Documentation & Repo Setup
- Authored detailed system design documentation (`docs/architecture-note.md` and `docs/product-note.md`).
- Documented deployment steps, local startup procedures, and evaluation guidelines.

---

## AI Tool Usage

Built with **Antigravity (Google DeepMind)** as the AI coding assistant. Used for:
- Scaffolding all backend modules (LangGraph nodes, repository layer, tool definitions)
- Writing the test suite
- Generating the Next.js frontend components
- Authoring the architecture and product notes

All design decisions, precedence rules, and access control logic were reviewed and specified by the developer; the AI translated them into code.
