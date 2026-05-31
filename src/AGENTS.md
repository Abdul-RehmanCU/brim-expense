# src/AGENTS.md

This folder contains the React + TypeScript application.

## Responsibilities

- Implement the client-side app, typed services, page views, hooks, reusable components, and frontend-safe wrappers.
- Keep business logic out of components.
- Keep server-only secrets out of this folder.

## Architecture rules

- Components render UI only.
- Hooks orchestrate frontend state and data fetching.
- `src/lib` contains import logic, frontend-safe domain helpers, and service wrappers.
- `src/types` contains shared TypeScript types.
- `src/pages` contains route-level screens.
- `src/components` contains reusable UI.
- `src/lib/api/backendClient.ts` is the preferred boundary for backend-owned domains such as policy, enrichment, risk, AI, approvals, and reports.
- `src/lib/ai` and other frontend wrappers may remain as transitional compatibility layers, but new business logic should favor the FastAPI backend.

## Security rules

- Only use `VITE_*` environment variables here.
- Never reference `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `SUPABASE_SERVICE_ROLE_KEY` in frontend code.
- Do not put API keys in React state, localStorage, logs, or error messages.

## Data integrity rules

- AI-generated text must not be treated as source-of-truth data.
- Spend totals, policy status, risk scores, approvals, and reports must come from database/tool outputs.
- Approval screens should render backend decision packets and allow human approve/deny decisions only. Missing information belongs in readiness/context UI, not as a third approval outcome.
- Reports should render backend-provided workflow metrics, citations, visuals, CSV export, and approval/readiness context.
- Synthetic demo data must remain visibly synthetic in code comments and seed logic.
- Use `businessCategory` as the finance-facing category name where possible, while preserving `normalizedCategory` compatibility until the migration is complete.
- The Policy Rules UI is a manager review surface, not a browser-side rules engine. It should call FastAPI endpoints through `src/lib/api/backendClient.ts` for rule listing, extraction, testing, activation, and scans.
- Do not call Claude, OpenAI, or service-role Supabase operations directly from the Policy Rules page or any React component.
- Draft AI-extracted rules must be shown as reviewable drafts and should not be presented as active policy until the backend reports them active.

## Styling

- Use Tailwind + shadcn/ui.
- Use Recharts for charts.
- Prioritize finance-manager clarity over decorative UI.
