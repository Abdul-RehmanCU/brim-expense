# src/components/dashboard/AGENTS.md

This folder contains dashboard components.

## Responsibilities

Render KPI cards, spend charts, and overview tables.

## Rules

- Keep components presentational whenever possible.
- Receive typed props from pages/hooks.
- Do not call Supabase, Claude, or OpenAI directly.
- Do not implement policy, risk, or report business logic here.
- Include loading/empty/error UI when useful.
