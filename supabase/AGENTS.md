# supabase/AGENTS.md

This folder owns Supabase schema, migrations, seeds, storage configuration, RLS, pgvector data, and optional Edge Functions.

## Responsibilities

- Define durable database schema in `migrations/`.
- Seed demo departments, employees, policy rules, and policy chunks in `seed/`.
- Support the frontend and backend with stable table contracts.
- Keep server-only AI and embedding work in trusted server-side code.

## Current architecture notes

- Supabase remains the system of record for imported transactions, synthetic business context, policy results, approvals, reports, and vector data.
- FastAPI is now the primary business-logic boundary.
- Edge Functions may still be used for secure AI or embedding workflows, but they are not the only server-side path anymore.

## Security rules

- Never expose `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` to frontend code.
- Use `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` only in the React client.
- Service role access belongs only in trusted server-side code such as FastAPI, Edge Functions, or local admin scripts.
- Do not log secrets, raw API keys, or full environment dumps.

## Database rules

- All durable records should use UUID primary keys unless there is a strong reason not to.
- Database columns should use snake_case.
- Add `created_at` timestamps to durable records.
- Preserve raw transaction data in `raw_transactions`; normalized data belongs in `transactions`.
- Use `business_category` as the finance-facing category column and keep `normalized_category` available for compatibility during migration.
- Mark synthetic demo records with `synthetic boolean default true` where relevant.
- Keep policy-check status names aligned with current backend contracts.
- Configurable policy-rule schema changes should extend `policy_rules` rather than replacing seeded demo rows in a breaking way.
- Policy rule JSON columns should remain data, not executable code. Store scopes, conditions, requirements, and outcomes as JSONB validated by the backend evaluator.
- AI-extracted rules should persist as `draft` or disabled until reviewed. Include source/review metadata such as source type, confidence, version, and human-review flags when the schema supports it.
- Add indexes for scan-time filters and active-rule lookups when introducing configurable rules, especially status/enabled, rule code, priority, and updated timestamps.

## RAG rules

- Policy RAG uses seeded policy text first.
- OpenAI embeddings are generated server-side only.
- Store embeddings in Supabase pgvector.
- RAG retrieves policy clauses for explanations; it does not calculate spend totals or enforce policy.

## Migration expectations

Each migration should be:

- ordered
- readable
- as safe and idempotent as practical
- consistent with existing live-demo data where possible
