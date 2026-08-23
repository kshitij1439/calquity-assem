# ParcelPilot Support Agent — Form Submission Notes

---

## 1. Repository
* **URL**: [https://github.com/kshitij1439/calquity-assem](https://github.com/kshitij1439/calquity-assem)
* **Setup & Run Instructions**: Available in `README.md` (supports Docker Compose one-step startup and local virtualenv execution).

---

## 2. Hosted Application
* **Frontend Web Application (Vercel)**: [https://calquity-assem.vercel.app](https://calquity-assem.vercel.app)
* **Backend API Service (Render)**: [https://calquity-assem.onrender.com](https://calquity-assem.onrender.com)
* **API Documentation (Swagger)**: [https://calquity-assem.onrender.com/docs](https://calquity-assem.onrender.com/docs)

> ⚡ **Cold Start Note for Reviewers**:
> The backend runs on Render's Free Instance tier. If inactive, the initial request wakes the container (~30-50 sec delay). **If the first attempt times out, please wait 15–30 seconds and retry.**

---

## 3. Demo Video Outline (5-Minute Structure)

* **0:00 - 1:00 | Architecture Overview**: Multi-node LangGraph DAG (`classify_and_route` → `lookup_data`/`rag` → `draft_answer`), Qdrant Cloud vector RAG, and Neon PostgreSQL operational database.
* **1:00 - 2:30 | Support Chat & RAG Demo**: Querying SLA rules, order cancellation policies, fee calculations, and source citation tool traces with active 3D Mascot UI.
* **2:30 - 3:30 | Operational Data & Human-in-the-Loop Gate**: Account context switching, multi-tenant data isolation, and two-phase JWT action confirmation for order cancellations.
* **3:30 - 4:30 | Proactive Issue & SLA Dashboard**: Live SLA breach detection, known issue clustering (`KI-208`, `KI-211`), and cross-customer spike alerts.
* **4:30 - 5:00 | Engineering Trade-offs**: Hybrid precedence resolution, deterministic Python safeguards, and dynamic LLM fallback (Groq → Gemini 2.5 Flash).

---

## 4. Architecture Note

### Agent Design
* Built using **LangGraph** state machine topology.
* Nodes: `classify_and_route`, `search_documents` (Vector RAG), `rank_precedence` (Deterministic Python sorter), `lookup_data` (Structured SQL queries), `draft_answer`, and `propose_action`.
* State retention ensures conversation thread continuity while enforcing strict role-based data isolation (`X-Account-ID`, `X-User-Role`).

### Tool Design
* **`search_documents`**: Queries Qdrant Cloud vector collections with payload filters excluding deprecated documents.
* **`query_operational_data`**: Parameterized SQL queries executing via repository pattern. LLM never writes raw SQL directly.
* **`propose_action` / `execute_action`**: Two-phase confirmation mechanism using 5-minute signed JWT tokens with idempotent execution.

### Document and Structured-Data Handling
* Unstructured PDFs (Ops SOPs, Account Contracts, General FAQs) are chunked and vectorized using **FastEmbed** into Qdrant.
* Structured data (Orders, Accounts, Tickets, Known Issues) resides in **PostgreSQL** with indexed relational foreign keys.

### Source Reliability and Conflict Handling
* Hierarchy enforced deterministically: **Account Contract Overrides > Operations SOP > General FAQs > Historical Tickets**.
* Deprecated documents filtered out at query time by database payload filters, eliminating prompt hallucination risk.

### Major Technical Trade-Offs
* **Deterministic Tool Execution vs. Dynamic Agent Loop**: Opted for a structured multi-node DAG over an open-ended autonomous agent loop to guarantee zero infinite loops, predictable latency, and reproducible audit logs.
* **Pre-baked SQL Repositories vs. Text-to-SQL**: Enforced typed repository functions instead of raw Text-to-SQL to guarantee 100% multi-tenant data isolation and prevent SQL injection.

---

## 5. Product Note

### Client Problem Addressed & Implementation
* **Selected Problem**: Proactive Operations & Cross-Customer SLA Breach Dashboard.
* **Implementation**: Built a real-time operational dashboard at `/dashboard` calculating SLA breach urgency scores against a snapshot reference time, clustering tickets by known issue references, and alerting on cross-customer ticket spikes within 24-hour windows.

### What Else Would Be Built for ParcelPilot
1. **Automated Carrier API Integration**: Direct webhooks into FedEx/UPS APIs for real-time tracking scan updates.
2. **Predictive SLA Risk Engine**: Machine learning model forecasting SLA breach probabilities before tickets exceed target response windows.

### Intentionally Left Out of Submission
* Unrestricted raw execution of database mutations (all write actions require human confirmation).
* Client-side auth credential storage (session boundaries enforced via HTTP headers).

### Primary Metric to Judge Product Usefulness
* **First Contact Resolution (FCR) Rate**: Percentage of support tickets resolved correctly on first turn without agent escalation.

---

## 6. AI Tool Usage
* Developed with **Antigravity (Google DeepMind)** as the AI pair-programming assistant.
* Used for architectural scaffolding, FastAPI route definitions, LangGraph node assembly, pytest test suite generation, Next.js frontend styling, and Three.js 3D mascot integration.
