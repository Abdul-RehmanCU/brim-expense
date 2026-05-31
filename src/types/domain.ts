export type UUID = string
export type ISODate = string
export type ISODateTime = string

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type PolicyStatus =
  | 'compliant'
  | 'excluded_non_expense'
  | 'review_required'
  | 'context_needed'
  | 'approval_evidence_needed'
  | 'policy_violation'
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type ApprovalStatus = 'draft' | 'requested' | 'approved' | 'denied' | 'cancelled'
export type ReportStatus = 'draft' | 'generated' | 'exported' | 'archived'
export type ChatRole = 'user' | 'assistant' | 'system' | 'tool'
export type ChartType = 'none' | 'table' | 'bar' | 'line' | 'pie'

export type Department = {
  id: UUID
  name: string
  managerName: string
  monthlyBudgetCad: number
  quarterlyBudgetCad: number
  synthetic: true
}

export type Employee = {
  id: UUID
  departmentId: UUID
  managerEmployeeId: UUID | null
  fullName: string
  email: string
  role: string
  synthetic: true
}

export type RawTransaction = {
  id: UUID
  sourceFileName: string | null
  sourceRowNumber: number
  sourceFingerprint: string
  rawPayload: Record<string, unknown>
  importBatchId: UUID | null
  syntheticContextAssigned: boolean
}

export type Transaction = {
  id: UUID
  rawTransactionId: UUID | null
  employeeId: UUID | null
  departmentId: UUID | null
  transactionCode: string | null
  description: string | null
  sourceCategory: string | null
  businessCategory: string
  normalizedCategory: string
  categoryConfidence: number
  postingDate: ISODate | null
  transactionDate: ISODate | null
  merchantName: string | null
  normalizedMerchantName: string | null
  amountOriginal: number
  amountCad: number
  debitCredit: 'debit' | 'credit'
  merchantCategoryCode: string | null
  merchantCity: string | null
  merchantCountry: string | null
  merchantPostalCode: string | null
  merchantRegion: string | null
  conversionRate: number | null
  syntheticAssignment: true
  sourceFingerprint?: string | null
  employeeName?: string | null
  departmentName?: string | null
}

export type Receipt = {
  id: UUID
  transactionId: UUID
  status: 'unavailable' | 'missing' | 'submitted' | 'approved' | 'rejected'
  storagePath: string | null
  fileName?: string | null
  receiptDate?: ISODate | null
  submittedAt: ISODateTime | null
  synthetic: boolean
}

export type Preapproval = {
  id: UUID
  employeeId: UUID
  transactionId: UUID | null
  departmentId?: UUID | null
  status: 'not_required' | 'missing' | 'requested' | 'approved' | 'denied'
  requestedAmountCad: number
  businessPurpose: string | null
  synthetic: boolean
}

export type PolicyRule = {
  id: UUID
  ruleCode: string
  title: string
  description: string
  severity: Severity
  deterministic: boolean
  active: boolean
  synthetic: boolean
}

export type PolicyViolation = {
  ruleCode: string
  severity: Severity
  explanation: string
  requiredAction: string
}

export type PolicyCheckResult = {
  transactionId: UUID
  status: PolicyStatus
  maxSeverity: Severity
  severityScore: number
  scanVersion: string | null
  violations: PolicyViolation[]
  missingInformation: string[]
  recommendedNextAction: string
}

export type RiskSignal = {
  type: string
  severity: Severity
  message: string
}

export type RiskScoreResult = {
  transactionId: UUID
  riskScore: number
  riskLevel: RiskLevel
  signals: RiskSignal[]
}

export type ApprovalRequest = {
  id: UUID
  transactionId: UUID
  employeeId: UUID
  departmentId: UUID
  status: ApprovalStatus
  requestedAmountCad: number
  aiRecommendation: ApprovalRecommendation | null
  contextSnapshot?: Record<string, unknown> | null
  reviewQueueItemId?: UUID | null
  decisionNote?: string | null
  decidedBy?: string | null
  decidedAt?: ISODateTime | null
}

export type ApprovalRecommendation = {
  recommendation: 'approve' | 'deny'
  confidence: 'low' | 'medium' | 'high'
  rationale: string
  groundedInputs: string[]
  missingInformation: string[]
  source?: 'deterministic_fallback' | 'openai_structured_output'
}

export type ExpenseReport = {
  id: UUID
  employeeId: UUID
  departmentId: UUID
  periodStart: ISODate
  periodEnd: ISODate
  status: ReportStatus
  totalAmountCad: number
  missingReceiptCount: number
  missingPreapprovalCount?: number
  approvalRequestCount?: number
  openApprovalCount?: number
  policyFlagCount: number
  riskFlagCount: number
  policyUnscannedCount?: number
  riskUnscannedCount?: number
  approvalReady?: boolean
  workflowStatus?: 'scan_incomplete' | 'action_required' | 'pending_cfo_review' | 'ready_for_cfo'
  blockerCount?: number
  approvalRecommendationCounts?: Record<string, number>
  cfoNextActions?: string[]
  reportName?: string | null
  reportSpec?: Record<string, unknown> | null
  aiSummary: string | null
  synthetic: boolean
}

export type PolicyChunk = {
  id: UUID
  documentId: UUID
  ruleCode: string | null
  chunkIndex: number
  content: string
  synthetic: boolean
}

export type QueryPlan = {
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
