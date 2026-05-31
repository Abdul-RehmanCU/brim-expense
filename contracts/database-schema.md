# Database Schema Contract

This contract defines the Supabase schema used by the current implementation. Database columns use snake_case. Durable records use UUID primary keys and `created_at`; mutable tables also use `updated_at`.

## Extensions

- `pgcrypto` for `gen_random_uuid()`.
- `vector` for policy RAG embeddings.
- `policy_chunks.embedding` uses `vector(1536)` for OpenAI `text-embedding-3-small`.

## Core Tables

### departments

Synthetic demo departments with budgets.

- `id uuid primary key`
- `name text unique not null`
- `manager_name text not null`
- `monthly_budget_cad numeric(12,2) not null`
- `quarterly_budget_cad numeric(12,2) not null`
- `synthetic boolean not null default true`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

### employees

Synthetic demo employees and managers.

- `id uuid primary key`
- `department_id uuid references departments(id)`
- `manager_employee_id uuid references employees(id)`
- `full_name text not null`
- `email text unique not null`
- `role text not null`
- `synthetic boolean not null default true`
- timestamps

### raw_transactions

Preserves original CSV-shaped rows.

- `id uuid primary key`
- `source_file_name text`
- `source_row_number integer not null`
- `source_fingerprint text unique not null`
- `raw_payload jsonb not null`
- `import_batch_id uuid`
- `synthetic_context_assigned boolean not null default false`
- `created_at timestamptz not null default now()`

`source_fingerprint` is derived from stable source fields so re-importing the same CSV does not duplicate transactions.

### transactions

Normalized card transactions with deterministic synthetic business context.

- `id uuid primary key`
- `raw_transaction_id uuid references raw_transactions(id)`
- `employee_id uuid references employees(id)`
- `department_id uuid references departments(id)`
- source fields: `transaction_code`, `description`, `source_category`, dates, merchant fields, MCC, conversion rate
- finance-facing category fields: `business_category`, with legacy `normalized_category` kept as a compatibility alias during migration
- normalized fields: `category_confidence`, `normalized_merchant_name`, `amount_original`, `amount_cad`, `debit_credit`
- context fields: `business_purpose`, `guest_names`, `synthetic_assignment boolean default true`
- timestamps

### receipts

Receipt status and storage references. Synthetic demo records must be marked with `synthetic = true`.

### preapprovals

Manager pre-authorization records. Synthetic demo records must be marked with `synthetic = true`.

## Policy, Risk, and Approval Tables

### policy_rules

Digitized deterministic policy rules. Existing seeded demo columns remain for compatibility; configurable rule work should extend this table rather than replacing it abruptly.

- `rule_code text unique not null`
- `title text not null`
- `description text not null`
- `severity text check ('low','medium','high','critical')`
- `deterministic boolean default true`
- `active boolean default true`
- `synthetic boolean default true`

Configurable-rule extensions should support:

- `status text` with `draft`, `active`, and `disabled`
- `priority integer`
- JSONB rule data: `scope_json`, `applies_to_json`, `conditions_json`, `context_requirements_json`, `requires_json`, `outcome_json`
- provenance/review fields: `source_type`, `source_text`, `created_by`, `editable`, `version`, `extraction_confidence`, `needs_human_review`

JSONB columns store declarative rule data only. Backend validation and evaluation decide whether a draft can become active.

### policy_checks

Saved deterministic policy engine outputs.

- `transaction_id uuid references transactions(id)`
- `status text check ('compliant','excluded_non_expense','review_required','context_needed','approval_evidence_needed','policy_violation')`
- `max_severity text`
- `severity_score integer`
- `scan_version text`
- `missing_information text[]`
- `recommended_next_action text`
- `engine_version text`

### violations

Policy rule findings linked to checks and transactions.

### risk_scores

Explainable deterministic risk outputs. `signals` is JSONB and must contain typed signal objects.

### approval_requests

Approval queue records linking transaction, employee, department, policy check, risk score, optional AI recommendation JSON, readiness/citation context, and the review queue item that promoted the request.

Approval workflow extensions:

- `review_queue_item_id uuid references review_queue_items(id)`
- `context_snapshot jsonb` stores the immutable transaction, employee, department, policy, risk, budget, spend-history, and review-queue facts used at recommendation/decision time
- `recommendation_source text` with `deterministic_fallback` or `openai_structured_output`
- `recommendation_generated_at timestamptz`

The snapshot is audit support. It must not replace deterministic policy/risk source tables. Human decisions are approve or deny only; missing information belongs in readiness/context metadata.

## Report Tables

### expense_reports

Employee report summary for a date range, including workflow metrics, citations, visuals, CSV export metadata, and approval/readiness context where supported by the implementation.

### expense_report_items

Line items linked to transactions.

## Policy RAG Tables

### policy_documents

Seeded policy source text. Synthetic seeded policy documents must be marked `synthetic = true`.

### policy_chunks

Policy clauses and embeddings used only for retrieval/explanation, never enforcement.

- `embedding vector(1536)`
- `rule_code text`
- `metadata jsonb`

## Audit and Chat Tables

### audit_log

Immutable action trail for imports, scans, approvals, reports, and admin changes.

### chat_sessions / chat_messages

Conversation records for Talk to Data. Messages store content and metadata, not secrets.

## Compatibility Notes

- Frontend domain types use camelCase and live in `src/types/domain.ts`.
- Supabase row types use snake_case and live in `src/types/database.ts`.
- Server-only keys are not represented in the schema or frontend types.
- New category work should read `business_category` first. Existing `normalized_category` values remain populated so older UI/import paths do not break while the product migrates terminology.
