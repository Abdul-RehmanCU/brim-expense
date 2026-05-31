# src/types/AGENTS.md

This folder owns shared TypeScript types.

## Responsibilities

- Define canonical frontend/domain types.
- Mirror database entities where useful, but do not blindly expose database row shapes everywhere.
- Keep AI, policy, risk, approval, and report output types stable.

## Rules

- Use camelCase for TypeScript properties.
- Database-generated types may retain snake_case if generated from Supabase.
- Prefer explicit union types for statuses and severities.
- Do not duplicate the same type across multiple files.
- If a return shape is used by a tool, define it here and reference it from `contracts/tool-contract.md`.
- Prefer `businessCategory` as the finance-facing category property name.
- Keep `normalizedCategory` available as a compatibility alias until the migration is complete.

## Important status unions

Use stable values for:
- policy status
- risk level
- approval status
- report status
- AI intent
- chart type
