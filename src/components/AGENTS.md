# src/components/AGENTS.md

This folder contains reusable React components.

## Responsibilities

- Render reusable UI blocks.
- Keep components typed, small, and composable.
- Use Tailwind + shadcn/ui.
- Use Recharts only in chart components.

## Rules

- Do not put business logic in components.
- Do not call Claude, OpenAI, or Supabase directly from low-level components.
- Fetching belongs in hooks/pages; domain logic belongs in `src/lib`.
- Components should receive typed props and emit typed callbacks.
- Show loading, empty, and error states where appropriate.

## UX principles

- Finance-manager clarity over decoration.
- Tables should be scannable.
- Badges should make status/severity obvious.
- Charts should clarify spending, compliance, or risk.
