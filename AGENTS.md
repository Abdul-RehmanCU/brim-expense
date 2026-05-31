# AGENTS.md

# Brim Expense Intelligence Copilot - Root Agent Instructions

Read this file first. Then read `PROJECT_SPEC.md` before making changes.

Folder-level `AGENTS.md` files override or refine this guidance for their own directories.

---

## 0. Canonical Local Dev URLs

Unless the user explicitly asks for something different, use this local setup for the app:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

Assume `VITE_BACKEND_URL=http://localhost:8000` when running the frontend locally.

---

## 1. Current Architecture Snapshot

The repo now has two active application layers:

- `src/`: React + Vite + TypeScript frontend
- `backend/`: Python FastAPI backend for business logic

Current responsibility split:

- Frontend currently owns CSV parsing, normalization, deterministic categorization, synthetic employee assignment, and the working import flow.
- Backend owns policy scanning/checking, transaction enrichment, risk scoring, approvals, reports, AI orchestration, and backend API contracts.
- Supabase remains the database, auth, storage, and pgvector layer.
- Supabase Edge Functions still exist for secure AI/embedding work and compatibility, but they are no longer the primary business-logic boundary.

Do not break the current working React import flow while moving more logic toward FastAPI.

---

## 2. Core Product Rules

The product is a finance-manager copilot, not a generic AI demo.

Protect these behaviors:

1. Import CSV data
2. Normalize and categorize transactions
3. Persist demo-safe synthetic business context
4. Scan compliance deterministically
5. Surface explainable findings by transaction
6. Run risk, approvals, report, and AI workflows through backend APIs

Prefer grounded, inspectable outputs over cleverness.

---

## 3. Non-Negotiable Architecture Rules

### Backend Owns Business Logic

Policy, risk, RAG retrieval, AI orchestration, approvals, and reports belong behind the FastAPI `backend/` boundary.

Frontend code may keep transitional wrappers or prototypes, but it must not become the long-term source of truth for those domains.

Approval workflows are complete decision packets. Backend responses should include transaction, employee, department, policy, risk, budget, spend-history, citation/readiness, and audit context needed for a human to decide. The only durable human approval outcomes are approve and deny; missing context is represented in packet readiness/context fields, not as a separate approval decision outcome.

Reports are implemented backend-owned workflows. Report outputs should include workflow metrics, citations, visuals, CSV export, and approval/readiness context where relevant.

### AI Is Never the Source of Truth

Claude or other models may:

- explain data
- summarize findings
- help plan queries
- recommend actions

They may not:

- invent totals
- invent employees or departments
- invent compliance outcomes
- invent risk scores
- override deterministic backend logic

### No Server Secrets in the Browser

Never expose these in frontend code:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL`

Only `VITE_*` variables may be read in browser code.

### LLM-Generated SQL Guardrails

Do not execute arbitrary LLM-generated SQL by default.

Exception: the backend Talk to Data workflow may execute LLM-proposed SQL only when:

1. the SQL is generated server-side
2. a dedicated AI validator reviews it for read-only compliance
3. deterministic backend checks enforce single-statement read-only restrictions
4. execution runs inside a read-only transaction with explicit limits

If an AI system proposes a query plan, application code must validate and translate it into safe operations or into a validated read-only SQL execution path.

---

## 4. Data Reality and Synthetic Rules

The source CSV contains transaction-level fields only. It does not contain employees, departments, receipts, approvals, budgets, or attachments.

Therefore:

- synthetic employee and department assignment must remain clearly synthetic
- receipt and approval attachment absence must not be presented as confirmed missing documents
- evidence-related findings should mean "required or unavailable in the dataset," not "proven missing," unless explicit evidence records say so

Use deterministic logic only. No random demo assignment.

---

## 5. Category and Naming Rules

Use finance-facing names where possible.

- Prefer `business_category` as the primary finance-facing category field.
- Keep `normalized_category` available as a compatibility alias until the migration is fully complete.
- When both are present, new work should prefer `business_category`.

For category logic:

- obvious merchant or MCC rules should win before broad fallback rules
- permit and DOT-style merchants should outrank fuel when both could match
- account-side credits, redemptions, and refunds should be treated as excluded non-expense activity when deterministically identifiable

---

## 6. Policy Engine Rules

The Python backend policy engine is the authoritative compliance engine.

Policy rules are moving from fixed demo rules toward configurable, manager-reviewed rules. Preserve this split:

- AI may extract draft structured rules from policy text.
- Draft rules must be validated, reviewed, and activated before enforcement.
- Python evaluates active structured rules deterministically.
- AI explanations are on-demand summaries of persisted findings; they do not decide compliance.

Important policy behavior:

- findings are grouped by transaction for API and UI display
- individual violations are still persisted internally
- receipt-related items use evidence wording, not "missing receipt" wording by default
- receipt evidence should not dominate top-level compliance status
- category-specific receipt expectations belong in nested details

Current top-level policy statuses are:

- `policy_violation`
- `approval_evidence_needed`
- `context_needed`
- `review_required`
- `excluded_non_expense`
- `compliant`

Use transaction-level findings with nested violations by default.

Configurable rule work should keep compatibility with the current seeded Brim demo rules while adding a path for manager-defined policies. Do not leave two competing compliance sources of truth; if hardcoded behavior remains during migration, document whether it is fallback, seeded-rule compatibility, or temporary scaffolding.

---

## 7. Current Repo Boundaries

Prefer these ownership boundaries:

- `backend/app/services`: backend business logic
- `backend/app/tools`: MCP-style internal backend tools
- `backend/app/routers`: thin FastAPI routers
- `src/lib/import`: CSV parsing/import orchestration
- `src/lib/normalization`: deterministic row normalization
- `src/lib/categorization`: deterministic category assignment
- `src/lib/supabase`: browser-safe Supabase access only
- `src/lib/api/backendClient.ts`: frontend boundary to FastAPI
- `src/pages`: route-level orchestration
- `src/components`: reusable UI
- `supabase/migrations` and `supabase/seed`: durable schema and demo data

Do not put new durable policy or risk logic in React components.

---

## 8. Tools and MCP-Style Design

Do not build a real MCP server unless explicitly requested.

Internal tool-style orchestration should prefer backend Python modules in `backend/app/tools`.

Frontend tool helpers in `src/lib/tools` may remain for compatibility or local UI workflows, but new authoritative tool contracts should favor the backend boundary.

---

## 9. Testing Expectations

Use:

- `npm test` / Vitest for frontend and TypeScript logic
- `python -m pytest` in `backend/` for backend services and API routes

Keep tests deterministic. Do not call real external AI services from unit tests.

High-priority test areas:

- CSV parsing and normalization
- deterministic categorization
- synthetic assignment stability
- policy status priority
- grouped transaction findings
- evidence wording behavior
- backend route contracts

---

## 10. Delivery Rules

Before changing a feature:

1. Read the root `AGENTS.md`.
2. Read the folder-level `AGENTS.md` files for the files you will edit.
3. Check whether the current frontend or backend is the source of truth for that behavior.
4. Preserve working import and demo flows unless the user explicitly asks to migrate them.
5. Run the smallest useful verification for the surface you touched.

When unsure, choose the option that:

1. preserves working end-to-end behavior
2. keeps outputs grounded in real persisted data
3. keeps secrets server-side
4. maintains deterministic policy behavior
5. reduces migration risk between frontend and backend

Working software with accurate boundaries beats ambitious drift.
