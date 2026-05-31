# src/pages/AGENTS.md

This folder contains route-level screens.

## Responsibilities

- Compose hooks, services, and components into full user workflows.
- Keep page-level orchestration readable.
- Delegate business logic to `src/lib`.
- Delegate reusable visual pieces to `src/components`.
- Prefer backend API clients for backend-owned workflows.

## Required pages

- Dashboard
- Import
- Talk to Data
- Transactions
- Compliance
- Risk Radar
- Approvals
- Reports
- Policy Rules

## Rules

- Pages may call hooks.
- Pages should not contain complex policy/risk logic.
- Keep the current frontend import flow intact unless a migration is explicitly requested.
- Compliance, Risk Radar, Talk to Data, Approvals, and Reports should use backend endpoints for backend-owned workflows.
- Approvals pages should render complete decision packets and support human approve/deny decisions only.
- Reports pages should surface workflow metrics, citations, visuals, CSV export, and approval/readiness context from backend results.
- Policy Rules pages may orchestrate draft authoring and endpoint calls, but rule validation/execution semantics must stay behind the FastAPI boundary.
- Every page should have useful loading/empty/error states.
- Preserve the demo narrative: import data -> analyze spend -> scan compliance -> review risk -> approve -> generate report.
