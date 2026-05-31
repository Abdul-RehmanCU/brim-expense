export type BackendHealthResponse = {
  status: string
  service: string
}

export type BackendTransactionsSummary = {
  raw_transaction_count: number
  normalized_transaction_count: number
  employee_count: number
  department_count: number
}

export type PolicySeverity = 'low' | 'medium' | 'high' | 'critical'
export type PolicyRuleStatus = 'active' | 'draft' | 'disabled'
export type PolicyStatus =
  | 'compliant'
  | 'excluded_non_expense'
  | 'review_required'
  | 'context_needed'
  | 'approval_evidence_needed'
  | 'policy_violation'

export type PolicyViolation = {
  rule_code: string
  severity: PolicySeverity
  explanation: string
  required_action: string
}

export type PolicyCheckResult = {
  transaction_id: string
  status: PolicyStatus
  max_severity: PolicySeverity
  severity_score: number
  scan_version: string | null
  violations: PolicyViolation[]
  missing_information: string[]
  recommended_next_action: string
}

export type PolicyScanRequest = {
  department_id?: string | null
  employee_id?: string | null
  date_start?: string | null
  date_end?: string | null
  batch_size?: number
  limit?: number | null
  dry_run?: boolean
  reset_existing?: boolean
  reset_synthetic_evidence?: boolean
}

export type PolicyScanSummary = {
  total_scanned: number
  compliant: number
  excluded_non_expense: number
  evidence_required: number
  approval_evidence_required: number
  approval_evidence_needed: number
  context_needed: number
  policy_violations: number
  policy_violation: number
  review_required: number
  high_or_critical: number
  individual_flags: number
  violations_created: number
  duration_ms: number
  batch_count: number
}

export type TransactionEnrichmentRequest = {
  batch_size?: number
  limit?: number | null
  dry_run?: boolean
}

export type TransactionEnrichmentResponse = {
  total_seen: number
  updated: number
  skipped: number
  errors: number
  duration_ms: number
  batch_count: number
  error_messages: string[]
}

export type TransactionResetResponse = {
  deleted_transactions: number
  deleted_raw_transactions: number
  deleted_receipts: number
  deleted_preapprovals: number
  deleted_policy_checks: number
  deleted_violations: number
  deleted_risk_scores: number
  deleted_approval_requests: number
  deleted_expense_report_items: number
  deleted_expense_reports: number
}

export type DataQualitySeverity = 'low' | 'medium' | 'high' | 'critical'

export type DataQualityFinding = {
  rule_id: string
  severity: DataQualitySeverity
  field: string | null
  transaction_id: string | null
  source_row: number | null
  source_fingerprint: string | null
  row_index: number | null
  observed_value: unknown
  explanation: string
  remediation: string
}

export type DataQualitySummary = {
  row_count: number
  finding_count: number
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
  rows_with_findings: number
}

export type GreatExpectationsAudit = {
  available: boolean
  suite_name: string
  evaluated_expectations: number
  failed_expectations: number
  error: string | null
}

export type DataQualityValidationRequest = {
  rows: Record<string, unknown>[]
  run_great_expectations?: boolean
}

export type DataQualityValidationResponse = {
  row_count: number
  findings: DataQualityFinding[]
  summary: DataQualitySummary
  great_expectations: GreatExpectationsAudit
}

export type TransactionImportRow = {
  source_row_number: number
  source_fingerprint: string
  raw_payload: Record<string, unknown>
  transaction: Record<string, unknown>
}

export type TransactionImportRequest = {
  source_file_name?: string | null
  rows: TransactionImportRow[]
  run_data_quality?: boolean
  run_great_expectations?: boolean
  dry_run?: boolean
}

export type TransactionImportResponse = {
  inserted_count: number
  skipped_duplicate_count: number
  import_batch_id: string
  validation: DataQualityValidationResponse
  persisted: boolean
  authoritative_enrichment_applied: number
  warnings: string[]
}

export type ViolationListItem = {
  id: string
  transaction_id: string
  policy_check_id: string
  rule_code: string
  status: PolicyStatus
  severity: PolicySeverity
  explanation: string
  required_action: string
  transaction_date: string | null
  merchant: string | null
  amount_cad: number
  category: string
  employee: string | null
  department: string | null
}

export type PolicyFindingItem = {
  transaction_id: string
  employee: string | null
  department: string | null
  date: string | null
  merchant: string | null
  amount_cad: number
  category: string
  overall_status: PolicyStatus
  max_severity: PolicySeverity
  severity_score: number
  scan_version: string | null
  violations: PolicyViolation[]
  missing_information: string[]
  recommended_next_action: string
}

export type RepeatOffenderItem = {
  id: string | null
  name: string
  open_violations: number
}

export type RepeatOffenderSummary = {
  employees: RepeatOffenderItem[]
  departments: RepeatOffenderItem[]
}

export type PolicyRuleItem = {
  id: string
  rule_code: string
  name: string
  description: string
  severity: PolicySeverity
  enabled: boolean
  status: PolicyRuleStatus
  deterministic: boolean
  source_type: string
  source_text: string | null
  rule_json: Record<string, unknown>
  policy_document_id: string | null
  policy_extraction_run_id: string | null
  extraction_confidence: number | null
  needs_human_review: boolean
  validation_errors: string[]
  updated_at: string | null
}

export type PolicyRuleWriteRequest = {
  rule_code: string
  name: string
  description: string
  severity: PolicySeverity
  enabled?: boolean
  status?: PolicyRuleStatus
  source_type?: string
  source_text?: string | null
  rule_json?: Record<string, unknown>
}

export type PolicyRulePatchRequest = Partial<PolicyRuleWriteRequest>

export type PolicyRuleTestRequest = {
  rule_json?: Record<string, unknown>
  sample_limit?: number
}

export type PolicyRuleTestResponse = {
  valid: boolean
  matched_count: number
  sample_matches: Record<string, unknown>[]
  warnings: string[]
  validation_errors: string[]
  estimated_impact: {
    by_department: Record<string, number>
    by_employee: Record<string, number>
    by_category: Record<string, number>
  }
}

export type PolicyDocumentItem = {
  id: string
  title: string
  version: string
  source_type: 'seed' | 'pasted_text' | 'uploaded_pdf'
  file_name: string | null
  storage_path: string | null
  raw_text: string | null
  extracted_text: string | null
  extraction_status: 'pending' | 'extracted' | 'failed'
  extraction_error: string | null
  active: boolean
  synthetic: boolean
  created_at: string | null
  updated_at: string | null
}

export type PolicyDocumentCreateRequest = {
  title: string
  policy_text: string
}

export type PolicyDocumentCreateResponse = {
  policy_document_id: string
  document: PolicyDocumentItem
  text_preview: string
  char_count: number
}

export type PolicyDocumentExtractRequest = {
  company_context?: string | null
  available_fields?: string[] | null
}

export type PolicyExtractionRunItem = {
  id: string
  policy_document_id: string
  model_used: string | null
  status: 'pending' | 'completed' | 'failed'
  summary: string | null
  ambiguities: string[]
  unsupported_or_missing_fields: string[]
  suggested_feature_engineering: string[]
  draft_rule_count: number
  error: string | null
  created_at: string | null
}

export type ExtractedDraftRule = {
  id: string | null
  rule_code: string
  name: string
  description: string
  severity: PolicySeverity
  enabled: boolean
  status: PolicyRuleStatus
  source_type: string
  source_text: string | null
  rule_json: Record<string, unknown>
  policy_document_id: string | null
  policy_extraction_run_id: string | null
  extraction_confidence: number | null
  needs_human_review: boolean
  validation_errors: string[]
}

export type PolicyRuleExtractionResponse = {
  policy_document_id: string | null
  extraction_run: PolicyExtractionRunItem | null
  draft_rules: ExtractedDraftRule[]
  ambiguities: string[]
  unsupported_or_missing_fields: string[]
  suggested_feature_engineering: string[]
  summary: string
}

export type PolicyRuleExtractionRequest = {
  policy_text: string
  company_context?: string | null
  available_fields?: string[] | null
}

export type PolicyResetResponse = {
  rows_deleted: Record<string, number>
  storage_paths_removed: number
  warnings: string[]
}

export type ReportGenerateRequest = {
  request?: string | null
  employee_id?: string | null
  employee_name?: string | null
  department_id?: string | null
  department_name?: string | null
  date_start?: string | null
  date_end?: string | null
  refresh_workflow?: boolean
}

export type ExpenseReportLineItem = {
  id: string
  transaction_id: string
  transaction_date: string | null
  merchant: string | null
  amount_cad: number
  category: string
  receipt_status: string | null
  preapproval_status: string | null
  approval_status: string | null
  policy_status: string | null
  risk_level: string | null
  policy_scan_status: 'scanned' | 'unscanned'
  risk_scan_status: 'scanned' | 'unscanned'
  review_queue_item_id: string | null
  review_priority: number
  review_level: string | null
  reviewer_next_action: string | null
  approval_request_id: string | null
  approval_recommendation: 'approve' | 'deny' | null
  approval_recommendation_confidence: 'low' | 'medium' | 'high' | null
  approval_recommendation_rationale: string | null
  business_purpose: string | null
  guest_names: string[]
}

export type ReportVisualSpec = {
  id: string | null
  title: string
  subtitle: string | null
  chart_type: 'bar' | 'line' | 'pie' | 'table'
  dimension: 'employee' | 'department' | 'business_category' | 'month' | 'merchant'
  metric: 'sum_amount_cad' | 'transaction_count' | 'policy_flag_count' | 'risk_flag_count'
  limit: number
  sort_direction: 'asc' | 'desc'
}

export type ReportSpec = {
  title: string
  summary: string | null
  visuals: ReportVisualSpec[]
}

export type ReportVisualSeries = {
  key: string
  label: string
}

export type ReportVisualRow = {
  label: string
  values: Record<string, number>
}

export type ReportVisualResult = {
  id: string
  title: string
  subtitle: string | null
  chart_type: 'bar' | 'line' | 'pie' | 'table'
  dimension: 'employee' | 'department' | 'business_category' | 'month' | 'merchant'
  metric: 'sum_amount_cad' | 'transaction_count' | 'policy_flag_count' | 'risk_flag_count'
  series: ReportVisualSeries[]
  rows: ReportVisualRow[]
}

export type ExpenseReportSummary = {
  id: string
  employee_id: string
  employee_name: string | null
  report_name: string | null
  department_id: string
  department_name: string | null
  period_start: string
  period_end: string
  status: 'draft' | 'generated' | 'exported' | 'archived'
  total_amount_cad: number
  missing_receipt_count: number
  missing_preapproval_count: number
  approval_request_count: number
  open_approval_count: number
  policy_flag_count: number
  risk_flag_count: number
  policy_unscanned_count: number
  risk_unscanned_count: number
  approval_ready: boolean
  workflow_status: 'scan_incomplete' | 'action_required' | 'pending_cfo_review' | 'ready_for_cfo'
  blocker_count: number
  approval_recommendation_counts: Record<string, number>
  cfo_next_actions: string[]
  report_scope_type: 'employee' | 'department'
  grouping_reason: string | null
  ai_summary: string | null
  item_count: number
  created_at: string | null
  updated_at: string | null
}

export type ExpenseReportDetail = ExpenseReportSummary & {
  line_items: ExpenseReportLineItem[]
  report_spec: ReportSpec | null
  visuals: ReportVisualResult[]
  policy_clauses: CitedPolicyClause[]
}

export type ReportPlanTarget = {
  scope_type: 'employee' | 'department'
  requested_label: string
  resolved_label: string
  report_count: number
}

export type ReportGenerateResponse = {
  request: string | null
  planner_source: 'deterministic' | 'claude_fallback' | 'claude_critic'
  sql_preview: string | null
  generated_count: number
  targets: ReportPlanTarget[]
  warnings: string[]
  reports: ExpenseReportDetail[]
}

export type ExpenseReportListResponse = {
  reports: ExpenseReportSummary[]
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export type RiskSignal = {
  type: string
  severity: RiskLevel
  message: string
  evidence: Record<string, unknown>
}

export type CitedPolicyClause = {
  rule_code: string | null
  clause_id: string | null
  title: string | null
  text: string
  source: string | null
  match_score: number | null
}

export type ReviewerBrief = {
  summary: string
  key_reasons: string[]
  cited_policy_clauses: CitedPolicyClause[]
  missing_context: string[]
  recommended_next_action: string
  confidence: 'low' | 'medium' | 'high'
  grounding_warnings: string[]
  advisory_notice: string
  generated_by: 'deterministic_fallback' | 'openai_structured_output'
}

export type ApprovalStatus = 'draft' | 'requested' | 'approved' | 'denied' | 'cancelled'
export type ApprovalDecision = 'approved' | 'denied' | 'cancelled'

export type ApprovalRecommendation = {
  recommendation: 'approve' | 'deny'
  confidence: 'low' | 'medium' | 'high'
  rationale: string
  grounded_inputs: string[]
  missing_information: string[]
  source: 'deterministic_fallback' | 'openai_structured_output'
}

export type DepartmentBudgetStatus = {
  department_id: string | null
  department_name: string | null
  monthly_budget_cad: number
  quarterly_budget_cad: number
  month_to_date_spend_cad: number
  quarter_to_date_spend_cad: number
  monthly_remaining_cad: number
  quarterly_remaining_cad: number
  budget_period_month: string | null
  budget_period_quarter: string | null
  synthetic: boolean
}

export type EmployeeSpendHistory = {
  employee_id: string | null
  employee_name: string | null
  transaction_count: number
  total_spend_cad: number
  same_category_count: number
  same_category_spend_cad: number
  prior_approval_count: number
  prior_approved_count: number
}

export type ApprovalContextSnapshot = {
  transaction: Record<string, unknown>
  employee: Record<string, unknown>
  department: Record<string, unknown>
  policy: Record<string, unknown>
  risk: Record<string, unknown>
  budget: DepartmentBudgetStatus
  spend_history: EmployeeSpendHistory
  review_queue: Record<string, unknown>
}

export type ApprovalRequestCreate = {
  review_queue_item_id?: string | null
  transaction_id?: string | null
  requester_note?: string | null
  actor?: string | null
}

export type ApprovalDecisionRequest = {
  decision: ApprovalDecision
  actor?: string
  note?: string | null
}

export type ApprovalRequestItem = {
  id: string
  transaction_id: string
  employee_id: string
  employee_name: string | null
  department_id: string
  department_name: string | null
  approver_name: string | null
  status: ApprovalStatus
  requested_amount_cad: number
  transaction_date: string | null
  merchant: string | null
  category: string
  policy_check_id: string | null
  policy_status: PolicyStatus | null
  policy_severity: PolicySeverity | null
  policy_flags: PolicyViolation[]
  risk_score_id: string | null
  risk_score: number
  risk_level: RiskLevel | null
  risk_signals: RiskSignal[]
  ai_recommendation: ApprovalRecommendation | null
  reviewer_brief: ReviewerBrief | null
  budget_status: DepartmentBudgetStatus | null
  spend_history: EmployeeSpendHistory | null
  requester_note: string | null
  decision_note: string | null
  decided_by: string | null
  decided_at: string | null
  created_at: string | null
  updated_at: string | null
}

export type ApprovalRequestDetail = ApprovalRequestItem & {
  context_snapshot: ApprovalContextSnapshot | null
  audit_events: Record<string, unknown>[]
}

export type ApprovalListResponse = {
  approvals: ApprovalRequestItem[]
}

export type RiskScanRequest = {
  department_id?: string | null
  employee_id?: string | null
  date_start?: string | null
  date_end?: string | null
  limit?: number | null
  dry_run?: boolean
  reset_existing?: boolean
  split_window_days?: number
  anomaly_model?: 'auto' | 'pyod' | 'sklearn'
  detector_profile?: 'focused' | 'full'
}

export type RiskScanSummary = {
  total_scanned: number
  scored: number
  persisted: number
  high_or_critical: number
  signal_counts: Record<string, number>
  duration_ms: number
  engine_version: string
  dry_run: boolean
}

export type RiskScoreItem = {
  id: string | null
  transaction_id: string
  risk_score: number
  risk_level: RiskLevel
  signals: RiskSignal[]
  scored_at: string | null
  engine_version: string | null
  employee: string | null
  department: string | null
  transaction_date: string | null
  merchant: string | null
  amount_cad: number
  category: string
}

export type ReviewQueueItem = {
  id: string | null
  transaction_id: string
  employee: string | null
  employee_id: string | null
  department: string | null
  department_id: string | null
  transaction_date: string | null
  merchant: string | null
  amount_cad: number
  category: string
  queue_status: 'open' | 'in_approval' | 'resolved' | 'ignored'
  review_priority: number
  review_level: PolicySeverity
  policy_check_id: string | null
  policy_status: PolicyStatus | null
  policy_severity: PolicySeverity | null
  policy_flags: PolicyViolation[]
  risk_score_id: string | null
  risk_score: number
  risk_level: RiskLevel | null
  risk_signals: RiskSignal[]
  ai_context: string | null
  reviewer_brief: ReviewerBrief | null
  next_action: string
  generated_at: string | null
}

export type ReviewQueueSummary = {
  total: number
  open: number
  in_approval: number
  resolved: number
  ignored: number
  high_or_critical: number
  policy_flagged: number
  risk_flagged: number
}

export type ReviewQueueRefreshResponse = {
  generated: number
  persisted: number
  table_available: boolean
  summary: ReviewQueueSummary
}

export type InsightMode = 'answer' | 'chart' | 'table' | 'report'
export type InsightPlannerSource = 'deterministic' | 'deterministic_followup' | 'anthropic_structured' | 'claude_fallback'
export type InsightChatMessageRole = 'user' | 'assistant' | 'system' | 'tool'
export type InsightArtifactType = 'csv' | 'diagram' | 'brief'
export type InsightPageContext = {
  page?: string | null
  route?: string | null
  payload: Record<string, unknown>
}
export type InsightTool =
  | 'context.globalSummary'
  | 'spend.summary'
  | 'spend.groupBy'
  | 'spend.compare'
  | 'spend.topMerchants'
  | 'spend.topTransactions'
  | 'spend.sqlQuery'
  | 'review.currentQueue'
  | 'policy.latestFindings'
  | 'risk.latestSignals'
  | 'report.generate'
  | 'report.exportCsv'
  | 'policy.retrieveClauses'

export type InsightPlan = {
  intent: string
  mode: InsightMode
  tool: InsightTool
  filters: Record<string, unknown>
  group_by: string[]
  metrics: string[]
  sort: Record<string, unknown>[]
  limit: number
  visualization: string | null
  sql_statement?: string | null
  context_options?: Record<string, unknown>
  comparison_options: Record<string, unknown>
  report_options: Record<string, unknown>
}

export type InsightValidationResult = {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export type InsightPlanResponse = {
  question: string
  plan: InsightPlan
  validation: InsightValidationResult
  critic: InsightValidationResult
  planner_source: InsightPlannerSource
}

export type InsightQueryRequest = {
  question: string
  mode?: InsightMode | null
  session_id?: string | null
  page_context?: InsightPageContext | null
}

export type InsightResultRow = {
  label: string
  values: Record<string, unknown>
}

export type InsightCitation = {
  rule_code: string | null
  clause_id: string | null
  title: string | null
  text: string
  source: string | null
  match_score: number | null
}

export type InsightChatMessage = {
  id: string | null
  session_id: string | null
  role: InsightChatMessageRole
  content: string
  metadata: Record<string, unknown>
  created_at: string | null
}

export type InsightSession = {
  id: string
  title: string
  created_by_employee_id: string | null
  created_at: string | null
  updated_at: string | null
}

export type InsightSessionCreateRequest = {
  title?: string | null
  initial_question?: string | null
  page_context?: InsightPageContext | null
}

export type InsightSessionDetail = {
  session: InsightSession
  messages: InsightChatMessage[]
}

export type InsightArtifactDownload = {
  blob: Blob
  fileName: string
}

export type InsightQueryResponse = {
  question: string
  session_id: string | null
  plan: InsightPlan
  validation: InsightValidationResult
  planner_source: InsightPlannerSource
  summary: string
  columns: string[]
  rows: InsightResultRow[]
  citations: InsightCitation[]
  visualization: string | null
  metadata: Record<string, unknown>
}

const backendUrl = (import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000').replace(/\/$/, '')

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${backendUrl}${path}`, options)

  if (!response.ok) {
    let detail = `Backend request failed with status ${response.status}.`

    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string' && body.detail.trim()) {
        detail = body.detail
      }
    } catch {
      // Ignore JSON parsing failures and keep the generic status message.
    }

    throw new Error(detail)
  }

  return (await response.json()) as T
}

async function throwForBackendError(response: Response): Promise<never> {
  let detail = `Backend request failed with status ${response.status}.`

  try {
    const body = (await response.json()) as { detail?: string }
    if (typeof body.detail === 'string' && body.detail.trim()) {
      detail = body.detail
    }
  } catch {
    // Ignore JSON parsing failures and keep the generic status message.
  }

  throw new Error(detail)
}

export function getBackendHealth() {
  return fetchJson<BackendHealthResponse>('/health')
}

export function getBackendTransactionsSummary() {
  return fetchJson<BackendTransactionsSummary>('/transactions/summary')
}

export function planInsight(request: InsightQueryRequest) {
  return fetchJson<InsightPlanResponse>('/insights/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function queryInsights(request: InsightQueryRequest) {
  return fetchJson<InsightQueryResponse>('/insights/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function createInsightSession(request: InsightSessionCreateRequest = {}) {
  return fetchJson<InsightSessionDetail>('/insights/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function listInsightSessions(limit = 40) {
  return fetchJson<InsightSession[]>(`/insights/sessions?limit=${limit}`)
}

export function getInsightSession(sessionId: string) {
  return fetchJson<InsightSessionDetail>(`/insights/sessions/${sessionId}`)
}

export async function generateInsightArtifactFile(artifact: InsightArtifactType, result: InsightQueryResponse): Promise<InsightArtifactDownload> {
  const response = await fetch(`${backendUrl}/insights/artifacts/${artifact}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result }),
  })

  if (!response.ok) {
    await throwForBackendError(response)
  }

  return {
    blob: await response.blob(),
    fileName: parseContentDispositionFileName(response.headers.get('content-disposition')) ?? `insight.${artifact === 'diagram' ? 'mmd' : artifact === 'brief' ? 'md' : 'csv'}`,
  }
}

export async function downloadInsightArtifactFile(params: {
  artifact: InsightArtifactType
  sessionId: string
  messageId?: string | null
}): Promise<InsightArtifactDownload> {
  const path = params.messageId
    ? `/insights/sessions/${params.sessionId}/messages/${params.messageId}/artifacts/${params.artifact}`
    : `/insights/sessions/${params.sessionId}/artifacts/${params.artifact}`
  const response = await fetch(`${backendUrl}${path}`)

  if (!response.ok) {
    await throwForBackendError(response)
  }

  return {
    blob: await response.blob(),
    fileName:
      parseContentDispositionFileName(response.headers.get('content-disposition')) ??
      `insight.${params.artifact === 'diagram' ? 'mmd' : params.artifact === 'brief' ? 'md' : 'csv'}`,
  }
}

export function enrichExistingTransactions(request: TransactionEnrichmentRequest = {}) {
  return fetchJson<TransactionEnrichmentResponse>('/transactions/enrich-existing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function validateTransactionDataQuality(request: DataQualityValidationRequest) {
  return fetchJson<DataQualityValidationResponse>('/transactions/data-quality', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function importTransactions(request: TransactionImportRequest) {
  return fetchJson<TransactionImportResponse>('/transactions/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function resetTransactions() {
  return fetchJson<TransactionResetResponse>('/transactions/reset', {
    method: 'DELETE',
  })
}

export function scanPolicy(request: PolicyScanRequest = {}) {
  return fetchJson<PolicyScanSummary>('/policy/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function getPolicySummary() {
  return fetchJson<PolicyScanSummary>('/policy/summary')
}

export function listPolicyViolations(filters: { severity?: string; status?: string; department_id?: string } = {}) {
  const query = new URLSearchParams()

  for (const [key, value] of Object.entries(filters)) {
    if (value) {
      query.set(key, value)
    }
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<ViolationListItem[]>(`/policy/violations${suffix}`)
}

export function listPolicyFindings(filters: { severity?: string; status?: string; department_id?: string } = {}) {
  const query = new URLSearchParams()

  for (const [key, value] of Object.entries(filters)) {
    if (value) {
      query.set(key, value)
    }
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<PolicyFindingItem[]>(`/policy/findings${suffix}`)
}

export function getPolicyRepeatOffenders() {
  return fetchJson<RepeatOffenderSummary>('/policy/repeat-offenders')
}

export function listPolicyRules(filters: { limit?: number; offset?: number; status?: PolicyRuleStatus } = {}) {
  const query = new URLSearchParams()
  if (filters.limit) {
    query.set('limit', String(filters.limit))
  }
  if (filters.offset) {
    query.set('offset', String(filters.offset))
  }
  if (filters.status) {
    query.set('status', filters.status)
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<PolicyRuleItem[]>(`/policy/rules${suffix}`)
}

export function resetPolicyData() {
  return fetchJson<PolicyResetResponse>('/policy/reset', {
    method: 'DELETE',
  })
}

export function createPolicyRule(request: PolicyRuleWriteRequest) {
  return fetchJson<PolicyRuleItem>('/policy/rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function updatePolicyRule(ruleId: string, request: PolicyRulePatchRequest) {
  return fetchJson<PolicyRuleItem>(`/policy/rules/${ruleId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function testPolicyRule(ruleId: string, request: PolicyRuleTestRequest = {}) {
  return fetchJson<PolicyRuleTestResponse>(`/policy/rules/${ruleId}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function testDraftPolicyRule(request: PolicyRuleTestRequest = {}) {
  return fetchJson<PolicyRuleTestResponse>('/policy/rules/test-draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function createPolicyDocumentFromText(request: PolicyDocumentCreateRequest) {
  return fetchJson<PolicyDocumentCreateResponse>('/policy/documents/from-text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export async function uploadPolicyDocumentPdf(file: File, title?: string) {
  const body = new FormData()
  body.set('file', file)
  if (title?.trim()) {
    body.set('title', title.trim())
  }

  return fetchJson<PolicyDocumentCreateResponse>('/policy/documents/upload', {
    method: 'POST',
    body,
  })
}

export function extractPolicyRulesFromDocument(policyDocumentId: string, request: PolicyDocumentExtractRequest = {}) {
  return fetchJson<PolicyRuleExtractionResponse>(`/policy/documents/${policyDocumentId}/extract-rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function extractPolicyRules(request: PolicyRuleExtractionRequest) {
  return fetchJson<PolicyRuleExtractionResponse>('/policy/rules/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function checkTransactionPolicy(transactionId: string, resetSyntheticEvidence = false) {
  const query = resetSyntheticEvidence ? '?reset_synthetic_evidence=true' : ''

  return fetchJson<PolicyCheckResult>(`/policy/check/${transactionId}${query}`, {
    method: 'POST',
  })
}

export function generateExpenseReport(request: ReportGenerateRequest = {}) {
  return fetchJson<ReportGenerateResponse>('/reports/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function listExpenseReports(filters: { limit?: number; offset?: number } = {}) {
  const query = new URLSearchParams()
  if (filters.limit) {
    query.set('limit', String(filters.limit))
  }
  if (filters.offset) {
    query.set('offset', String(filters.offset))
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<ExpenseReportListResponse>(`/reports${suffix}`)
}

export function getExpenseReport(reportId: string) {
  return fetchJson<ExpenseReportDetail>(`/reports/${reportId}`)
}

export function getExpenseReportCsvUrl(reportId: string) {
  return `${backendUrl}/reports/${reportId}/csv`
}

export function scanRisk(request: RiskScanRequest = {}) {
  return fetchJson<RiskScanSummary>('/risk/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function listRiskScores(filters: { min_level?: RiskLevel; limit?: number; signal_type?: string } = {}) {
  const query = new URLSearchParams()

  if (filters.min_level) {
    query.set('min_level', filters.min_level)
  }
  if (filters.limit) {
    query.set('limit', String(filters.limit))
  }
  if (filters.signal_type) {
    query.set('signal_type', filters.signal_type)
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<RiskScoreItem[]>(`/risk/scores${suffix}`)
}

export function refreshReviewQueue(request: { limit?: number | null; reset_existing?: boolean; persist?: boolean } = {}) {
  return fetchJson<ReviewQueueRefreshResponse>('/review-queue/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function listReviewQueueItems(
  filters: {
    limit?: number
    offset?: number
    queue_status?: ReviewQueueItem['queue_status']
    review_level?: PolicySeverity
    policy_status?: PolicyStatus
  } = {},
) {
  const query = new URLSearchParams()

  if (filters.limit) {
    query.set('limit', String(filters.limit))
  }
  if (filters.offset) {
    query.set('offset', String(filters.offset))
  }
  if (filters.queue_status) {
    query.set('queue_status', filters.queue_status)
  }
  if (filters.review_level) {
    query.set('review_level', filters.review_level)
  }
  if (filters.policy_status) {
    query.set('policy_status', filters.policy_status)
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<ReviewQueueItem[]>(`/review-queue/items${suffix}`)
}

export function listApprovals(filters: { status?: ApprovalStatus; limit?: number; offset?: number } = {}) {
  const query = new URLSearchParams()

  if (filters.status) {
    query.set('status', filters.status)
  }
  if (filters.limit) {
    query.set('limit', String(filters.limit))
  }
  if (filters.offset) {
    query.set('offset', String(filters.offset))
  }

  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson<ApprovalListResponse>(`/approvals${suffix}`)
}

export function createApprovalRequest(request: ApprovalRequestCreate) {
  return fetchJson<ApprovalRequestDetail>('/approvals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

export function getApprovalRequest(approvalId: string) {
  return fetchJson<ApprovalRequestDetail>(`/approvals/${approvalId}`)
}

export function decideApprovalRequest(approvalId: string, request: ApprovalDecisionRequest) {
  return fetchJson<ApprovalRequestDetail>(`/approvals/${approvalId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
}

function parseContentDispositionFileName(header: string | null) {
  if (!header) {
    return null
  }

  const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utfMatch?.[1]) {
    return decodeURIComponent(utfMatch[1])
  }

  const basicMatch = /filename="?([^";]+)"?/i.exec(header)
  return basicMatch?.[1] ?? null
}
