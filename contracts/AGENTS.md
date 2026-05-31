# contracts/AGENTS.md

This folder defines shared contracts between all implementation areas. These files are the coordination layer for Codex subagents.

## Responsibilities

- Keep schema, domain types, tool outputs, AI JSON formats, UI flows, and demo flows aligned.
- Update contracts before implementing changes that affect more than one folder.
- Prefer explicit field names and stable return shapes over informal descriptions.

## Required contract files

- `database-schema.md`
- `domain-types.md`
- `tool-contract.md`
- `ai-contract.md`
- `ui-flow.md`
- `demo-flow.md`

## Rules

- Do not put implementation code in this folder.
- Do not duplicate conflicting definitions across contract files.
- If implementation differs from a contract, update the contract in the same change.
- Use snake_case for database columns.
- Use camelCase for TypeScript domain objects.
- Clearly mark synthetic employee, department, receipt, approval, and budget data as synthetic.

## Handoff format

When changing a contract, summarize:
1. What changed
2. Which folders are affected
3. Required migration or type updates
4. Backward compatibility notes
