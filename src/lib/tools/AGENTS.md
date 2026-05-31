# src/lib/tools/AGENTS.md

This folder contains frontend-side MCP-style helper functions and compatibility wrappers.

Primary tool-style orchestration now belongs in `backend/app/tools`.

## Responsibilities

- Provide stable tool-like helpers for frontend-safe workflows.
- Stay aligned with `contracts/tool-contract.md`.
- Keep tool inputs/outputs aligned with `contracts/tool-contract.md`.

## Rules

- This is MCP-style, not a real MCP server for now.
- Tools must be deterministic where possible.
- Claude may request tool usage, but tools execute in application code.
- Never expose raw SQL execution as a tool.
- Validate all tool inputs.
- Return structured JSON-compatible outputs.
- Do not add new authoritative policy, risk, approval, or report enforcement logic here without a matching backend design.

## Recommended tools

- `spend.query`
- `policy.checkTransaction`
- `policy.checkBatch`
- `risk.scoreTransaction`
- `risk.scoreBatch`
- `approval.createRequest`
- `report.generate`
- `policy.retrieveClauses`
