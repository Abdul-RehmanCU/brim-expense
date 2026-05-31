# src/lib/policy/AGENTS.md

This folder contains transitional frontend policy helpers and placeholders.

The authoritative compliance engine now lives in `backend/app/services/policy_engine.py`.

## Responsibilities

- Keep any remaining frontend policy helpers small and compatible with backend contracts.
- Provide UI-safe types or adapters only when needed.
- Avoid duplicating backend policy logic unless the user explicitly asks for a frontend-only prototype.

## Non-negotiable rule

Claude is not the compliance engine, and this folder is not the source of truth for compliance outcomes.

## Current contract expectations

- Keep status names aligned with backend values:
  - `policy_violation`
  - `approval_evidence_needed`
  - `context_needed`
  - `review_required`
  - `excluded_non_expense`
  - `compliant`
- Receipt-related details should use evidence wording, not default to "missing receipt."
- Transaction-level grouped findings are the preferred UI/API shape.
