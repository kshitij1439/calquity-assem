# ParcelPilot Support Agent — Product Note

## 1. Additional Problem Chosen: Proactive Issue Detection

**Problem 1** was chosen: a dashboard that proactively surfaces SLA breaches, recurring known issues, and cross-customer patterns without requiring anyone to ask a question first.

### Why this problem
The chat agent is reactive — it only helps when someone already knows what to ask. The dashboard flips this: it tells the team what deserves attention right now. SLA breaches that are already overdue, tickets referencing the same known issue across multiple accounts, and unusual spikes are exactly the signals a 20-person ops team needs to prioritise their morning.

### How it was addressed
- **SLA breach detection**: Pure Postgres aggregation comparing `ticket.created_at` to `SNAPSHOT_NOW` against plan/contract-specific targets. No LLM involved — detection is deterministic.
- **Known-issue clusters**: `GROUP BY known_issue_ref` to surface KI-208 (Bulk Upload failures) and KI-211 (SwiftShip webhook delay) ticket volumes.
- **Cross-customer spikes**: Same `issue_type` across ≥2 distinct accounts within a 24-hour window — a simple `HAVING COUNT(DISTINCT account_id) >= 2` query.
- **Optional LLM summary**: A single isolated LLM call per cluster generates a one-line human-readable description. This is completely decoupled from the chat agent — a hallucination here doesn't affect answer trustworthiness.

---

## 2. What I'd Build Next

### Priority 1: Real-time streaming responses
The current `/chat` endpoint returns a full response. Streaming would reduce perceived latency significantly for longer answers.

### Priority 2: Postgres-backed checkpointer
Swap `MemorySaver` for `PostgresSaver` so conversation threads survive server restarts and can be inspected for debugging.

### Priority 3: Eval pipeline
A structured eval harness that runs the 4 test query types against the live agent weekly, logs `confidence`, `sources_used`, and `escalate`, and alerts when accuracy drops — treating the agent like a service with an SLA.

### Priority 4: Customer-facing context
The current agent is internal-staff-only. A customer-facing variant would need stricter data scoping (customers never see other accounts' ticket history even as tier-4 context), a softer escalation tone, and rate limiting.

### Priority 5: Feedback loop
A thumbs up/down on each agent response, stored in Postgres, feeding back into eval. The most common "thumbs down" queries become new test cases.

---

## 3. What Was Intentionally Left Out

- **Real authentication**: Headers are mocked. A production system needs JWT verification against an IdP.
- **Real action integrations**: `execute_action` is mocked. Wiring it to a ticketing system (e.g., Freshdesk, Zendesk) is a pure additive change behind the existing tool interface.
- **Streaming**: Response returned as a single block; streaming is a frontend/FastAPI addition that doesn't change the agent logic.
- **Multi-turn memory**: Thread ID supports it structurally, but conversation history injection into the prompt is minimal. A production agent would summarise older turns.
- **Hosted deployment**: Docker Compose is production-ready locally. Render + Vercel deployment is documented in the README but not wired in CI.

---

## 4. Success Metric

**Resolution rate without escalation, segmented by confidence level.**

Specifically: the percentage of queries where `confidence=high` and `escalate=false`, measured weekly. A useful agent should resolve ≥70% of routine queries (cancellation eligibility, SLA checks, policy lookups) without human intervention, while correctly escalating the genuinely uncertain cases. Tracking the escalation rate by query type also surfaces which document gaps or data quality issues are causing the most uncertainty.
