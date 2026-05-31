# MCP-Style Internal Tool Contract

The tool layer is internal and MCP-style only. It is not a real MCP server in this version.

Rules:

- Tools accept typed input and return typed output.
- Tools validate inputs.
- Tools do not import React UI.
- Tools do not call Claude or OpenAI directly.
- Tools may execute LLM-proposed SQL only when backend code runs a dedicated read-only validation workflow first, including an AI SQL critic plus deterministic safety gates, and the final execution stays inside a read-only transaction.
- Mutation tools must be named as mutations or actions.

## Tool Names

### spend.query

Input: validated filters, optional group by, and metric.

Output: rows, totals, and optional chart-ready series derived from database rows.

### spend.sqlQuery

Input: a user request plus page/session context that may require ad hoc SQL.

Output: rows, columns, totals, and optional chart-ready series from a validated read-only SQL statement. The backend must record the generated SQL, validator decision, and execution metadata.

### spend.dashboardSummary

Input: date range and optional department filter.

Output: total spend, transaction count, missing receipts, open policy flags, high-risk count, and department budget snapshots.

### policy.checkTransaction

Input: transaction, receipt context, preapproval context, and policy rules.

Output: `PolicyCheckResult`.

### policy.checkBatch

Input: transaction ids or normalized transaction objects.

Output: persisted policy checks and violations.

### policy.rules.list

Input: optional status, enabled, source type, and search filters.

Output: configured policy rules with validation state and review metadata.

### policy.rules.testDraft

Input: draft structured rule JSON and optional sample filters.

Output: matched count, sample matches, warnings, and estimated impact. This must not persist policy checks.

### policy.rules.activate

Input: rule id and manager/reviewer context.

Output: activated rule record or validation errors. Draft AI rules must pass backend validation before activation.

### policy.rules.extract

Input: policy text, optional company context, and optional available fields.

Output: draft rules, ambiguities, unsupported or missing fields, suggested feature engineering, and summary. Extracted rules are drafts, not active enforcement.

### policy.retrieveClauses

Input: query text, optional rule codes, topK, threshold.

Output: matching policy chunks with similarity. Used for explanations only.

### risk.scoreTransaction

Input: transaction plus employee, department, policy, and history features.

Output: `RiskScoreResult`.

### risk.scoreBatch

Input: transaction ids or feature set.

Output: persisted risk scores.

### approval.createRequest

Input: review queue item id or transaction id, optional actor, and optional requester note.

Output: durable approval request detail with context snapshot, budget status, spend history, policy/risk facts, and advisory recommendation.

### approval.decide

Input: approval request id, decision, actor, and note.

Output: updated request. The backend also updates related synthetic preapproval state, resolves the review queue item, and writes an audit log entry.

### report.generate

Input: employee id, period start, period end.

Output: expense report and line items from persisted transaction, policy, and risk data.

### report.exportCsv

Input: expense report id.

Output: CSV string or downloadable blob metadata.

## Tool Registry

`src/lib/tools/toolRegistry.ts` owns stable names and metadata. UI pages call hooks/services, not raw tool internals, once later milestones are implemented.
