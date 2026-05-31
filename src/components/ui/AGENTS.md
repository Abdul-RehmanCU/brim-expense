# src/components/ui/AGENTS.md

This folder contains shadcn/ui component wrappers.

## Responsibilities

Keep generated shadcn components minimally modified.

## Rules

- Keep components presentational whenever possible.
- Receive typed props from pages/hooks.
- Do not call Supabase, Claude, or OpenAI directly.
- Do not implement policy, risk, or report business logic here.
- Include loading/empty/error UI when useful.
