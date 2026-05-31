# src/lib/risk/AGENTS.md

This folder contains transitional frontend risk helpers and prototypes.

Authoritative risk scoring belongs to the FastAPI backend. Keep this folder limited to transitional frontend helpers unless the user explicitly asks otherwise.

## Responsibilities

- Build transaction features.
- Detect duplicate transactions.
- Detect split transactions.
- Detect near-threshold behavior.
- Detect merchant novelty.
- Detect peer/department deviation.
- Detect unusual foreign activity.
- Produce explainable risk scores.

## Rules

- Start deterministic and explainable.
- Do not claim true fraud; say possible anomaly, risk, or review needed.
- Every risk score must include reasons/signals.
- Keep real ML optional and separate from deterministic review signals.
- Risk scoring must not override policy status; it complements policy checks.
- Do not make frontend prototypes the durable source of truth once backend risk endpoints exist.

## Required output

Return:
- transaction id
- risk score from 0 to 100
- risk level
- structured signals with type, severity, and message
