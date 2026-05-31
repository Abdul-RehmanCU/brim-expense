# src/lib/AGENTS.md

This folder contains domain logic and service wrappers.

## Responsibilities

- Keep business logic out of React components.
- Provide deterministic import, normalization, categorization, synthetic-assignment, and frontend-safe service modules.
- Keep modules small, typed, and testable.

## Rules

- Prefer pure functions where possible.
- Use dependency injection or function parameters instead of hidden global state.
- Avoid direct UI imports from `src/components` or `src/pages`.
- Do not access server-only environment variables.
- Use `src/lib/api/backendClient.ts` for backend-owned workflows.
- Frontend policy, risk, AI, RAG, approvals, and reports modules are transitional unless the user explicitly asks for frontend-only behavior.
- New authoritative policy, risk, approval, report, or AI orchestration logic should not be added here without coordinating the FastAPI source of truth.

## Testing expectations

Import, normalization, categorization, and synthetic assignment logic should be easy to unit test.
