# tests/AGENTS.md

This folder contains frontend Vitest tests.

Backend pytest coverage lives under `backend/app/tests`.

## Responsibilities

- Test deterministic business logic.
- Prioritize import, categorization, normalization, and synthetic assignment behavior that still lives in frontend code.

## Rules

- Tests should be fast and deterministic.
- Do not call real Claude, OpenAI, or Supabase from unit tests.
- Mock external clients.
- Include edge cases for malformed CSV values and conversion rates.
- Use evidence wording expectations when testing receipt-related frontend text or adapters.
- When a behavior is backend-owned, prefer adding or updating pytest coverage in `backend/app/tests` instead of rebuilding the same logic here.

## Minimum tests

- `normalization.test.ts`
- `syntheticAssignment.test.ts`
- `categorization.test.ts`
