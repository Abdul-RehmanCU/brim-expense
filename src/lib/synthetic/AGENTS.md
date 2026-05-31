# src/lib/synthetic/AGENTS.md

This folder owns the synthetic business layer required because the CSV is transaction-only.

## Responsibilities

- Seed or reference synthetic employees, departments, managers, and budgets.
- Assign transactions to employees/departments deterministically on import.
- Generate synthetic receipt and preapproval states.
- Create hero demo scenario data.

## Rules

- Be explicit that generated employee, department, receipt, approval, and budget data is synthetic.
- Do not pretend synthetic fields came from the original CSV.
- Use deterministic hashing for transaction assignment.
- Same CSV row should map to the same synthetic employee when re-imported.
- Keep the Sarah Chen / Marketing hero scenario stable.

## Recommended approach

- Seed employees/departments/managers/budgets once.
- Assign transactions deterministically during import.
- Generate realistic receipt/preapproval status during import.
