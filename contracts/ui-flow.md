# UI Flow Contract

The shell routes are live workflow surfaces. Keep this contract aligned with the current implementation rather than historical placeholder milestones.

## App Shell

- Persistent sidebar on desktop.
- Topbar with active page title and short description.
- Horizontal mobile navigation.
- Navigation routes:
  - `/dashboard`
  - `/import`
  - `/talk-to-data`
  - `/transactions`
  - `/compliance`
  - `/risk-radar`
  - `/approvals`
  - `/reports`
  - `/policy-rules`

## Page Responsibilities

- Dashboard: finance overview KPIs and charts.
- Import: CSV upload and import review.
- Talk to Data: chat and chart/table answers.
- Transactions: normalized transaction table after import.
- Compliance: deterministic policy scan results.
- Risk Radar: explainable risk signals from backend-owned risk workflows.
- Approvals: promotes merged review queue items into durable approval requests, shows complete policy/risk/budget/history/citation/readiness decision packets, and records human approve/deny decisions.
- Reports: expense report generation with workflow metrics, citations, visuals, CSV export, and approval/readiness context.
- Policy Rules: configurable policy rule review, including seeded, manual, and AI-extracted draft rules.

## UX Rules

- Finance-manager clarity over decoration.
- Synthetic fields must be labeled as synthetic/demo data.
- AI answers must show grounding or missing context.
- Do not hide deterministic policy or risk reasons.
- Policy Rules must make draft, active, and disabled states clear. AI-extracted rules are reviewable drafts until backend validation and manager activation succeed.
