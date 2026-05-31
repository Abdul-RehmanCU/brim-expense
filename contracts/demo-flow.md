# Demo Flow Contract

The primary demo remains:

1. Finance manager opens the Brim Expense Intelligence Copilot.
2. User imports the transaction CSV.
3. App confirms synthetic departments, employees, managers, receipts, approvals, and budgets.
4. Dashboard shows spend, compliance exposure, and risk summaries.
5. User asks: "What did Marketing spend this month by category?"
6. App returns grounded chart, table, and summary.
7. User asks: "How does that compare to Engineering?"
8. App answers using safe follow-up context.
9. User runs compliance scan.
10. App flags missing receipts, missing preapprovals, restricted alcohol, fines/tickets, and needs-context items.
11. User creates an approval request.
12. AI recommends approve or deny using persisted policy, risk, budget, readiness, citation, and history facts.
13. User generates Sarah Chen's synthetic Marketing expense report.
14. Report shows line items, policy flags, risk flags, workflow metrics, citations, visuals, approval/readiness context, summary, and CSV export.

## Hero Scenario

- Employee: Sarah Chen
- Department: Marketing
- Purpose: conference/travel expense report
- Data status: synthetic demo context layered over imported transaction-shaped data

## Current Scope

The current implementation includes CSV import, policy scans, risk scoring, AI-assisted approvals, and reports. Approvals are complete decision packets with human approve/deny only; missing context appears as readiness/context, not a request-information decision.
