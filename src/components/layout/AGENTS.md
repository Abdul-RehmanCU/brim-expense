# src/components/layout/AGENTS.md

This folder contains layout components.

## Responsibilities

Own app shell, sidebar, topbar, and page headers.

## Rules

- Keep components presentational whenever possible.
- Receive typed props from pages/hooks.
- Do not call Supabase, Claude, or OpenAI directly.
- Do not implement policy, risk, or report business logic here.
- Include loading/empty/error UI when useful.
