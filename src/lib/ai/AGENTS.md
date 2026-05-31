# src/lib/ai/AGENTS.md

This folder owns frontend-safe AI service wrappers and schemas.

New AI product work should prefer the FastAPI backend boundary unless the user explicitly asks for Supabase Edge Function work.

## Responsibilities

- Keep typed request/response contracts for AI-related frontend calls.
- Support legacy or compatibility wrappers without exposing secrets.
- Define AI request/response schemas.
- Keep prompt-facing contracts synchronized with `contracts/ai-contract.md`.

## Security rules

- Do not import Claude or OpenAI SDKs here.
- Do not read `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
- Do not expose prompts containing secrets.
- Browser code must call secure server-side boundaries only.

## AI behavior rules

- Claude must not invent numbers, totals, employees, departments, or policy decisions.
- Query planning returns JSON only.
- Approval recommendations must use tool/database outputs.
- Approval recommendations are approve/deny only; missing context belongs in readiness/context fields.
- Report summaries must cite computed report facts, not hallucinated facts.
- If data is missing, return missing data clearly.
