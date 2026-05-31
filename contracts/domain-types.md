# Domain Types Contract

TypeScript domain objects use camelCase and are defined in `src/types/domain.ts`. Database row types may retain snake_case in `src/types/database.ts`.

## Shared Scalars

- `UUID = string`
- `ISODate = string`
- `ISODateTime = string`

## Status Unions

- `Severity = 'low' | 'medium' | 'high' | 'critical'`
- `PolicyStatus = 'compliant' | 'excluded_non_expense' | 'review_required' | 'context_needed' | 'approval_evidence_needed' | 'policy_violation'`
- `RiskLevel = 'low' | 'medium' | 'high' | 'critical'`
- `ApprovalStatus = 'draft' | 'requested' | 'approved' | 'denied' | 'cancelled'`
- `ReportStatus = 'draft' | 'generated' | 'exported' | 'archived'`
- `ChatRole = 'user' | 'assistant' | 'system' | 'tool'`
- `ChartType = 'none' | 'table' | 'bar' | 'line' | 'pie'`

## Synthetic Data Types

Synthetic demo data must be visible in type names, fields, UI copy, seed files, or comments.

- `Department.synthetic` is `true` for seeded demo departments and budgets.
- `Employee.synthetic` is `true` for seeded demo employees.
- `Transaction.syntheticAssignment` is `true` when assigned by deterministic demo logic.
- `Receipt.synthetic`, `Preapproval.synthetic`, and `ExpenseReport.synthetic` mark generated demo context.

## Import Types

Import types are implemented in `src/lib/import/csvParser.ts` and related modules.

- Raw CSV rows preserve all original Brim fields exactly as strings.
- Required column validation fails fast with explicit missing column names.
- `sourceFingerprint` is a stable hash from transaction code, merchant, transaction date, amount, debit/credit, and source row number.
- Re-imports use the fingerprint to skip duplicate rows instead of appending a second copy.
- `Conversion Rate` of `0`, empty, or invalid means the row is already CAD; otherwise `amountCad = transactionAmount * conversionRate`.
- `businessCategory` is the finance-facing category name. `normalizedCategory` remains available as a compatibility alias and should mirror `businessCategory` until the older field is retired.

## Policy Check Output

```ts
type PolicyCheckResult = {
  transactionId: UUID
  status: PolicyStatus
  maxSeverity: Severity
  violations: PolicyViolation[]
  missingInformation: string[]
  recommendedNextAction: string
}
```

Policy checks are produced by deterministic backend services. RAG may retrieve clauses for explanation but does not decide status.

## Risk Score Output

```ts
type RiskScoreResult = {
  transactionId: UUID
  riskScore: number
  riskLevel: RiskLevel
  signals: RiskSignal[]
}
```

Risk scores must include explainable signals. Do not return a score without reasons.

## Approval Workflow Output

Approval requests are backend-owned. Creating a request from the review queue returns the durable request, advisory recommendation, budget status, spend history, readiness/context gaps, citations, and a context snapshot of the facts used for the recommendation.

Human decisions are approve or deny only and update the approval status and audit trail. Missing context is captured in packet readiness/context fields, not as a separate approval outcome. AI recommendations remain advisory.

## AI Query Plan

Claude may return a structured query plan. The app must validate it and translate it to safe query builder calls. Raw SQL from Claude is never executed.

```ts
type QueryPlan = {
  intent: 'spend_query' | 'policy_question' | 'risk_review' | 'approval_review' | 'report_request'
  filters: {
    dateStart: ISODate | null
    dateEnd: ISODate | null
    department: string | null
    employee: string | null
    category: string | null
    merchant: string | null
  }
  groupBy: 'department' | 'employee' | 'category' | 'merchant' | 'month' | null
  metric: 'sum_amount' | 'count_transactions' | 'avg_amount' | 'max_amount'
  visualization: ChartType
  needsClarification: boolean
  clarificationQuestion: string | null
}
```
