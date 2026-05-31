# src/lib/utils/AGENTS.md

This folder contains shared utilities.

## Responsibilities

- Date helpers
- Currency/number formatting
- Stable hashing
- Constants
- Small pure helpers

## Rules

- Keep utilities generic and dependency-light.
- Do not place business workflows here.
- Do not import React components.
- Stable hashing must be deterministic across browser sessions and imports.
