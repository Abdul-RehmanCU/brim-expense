// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AssistantProvider } from '@/lib/assistant/AssistantProvider'
import { TransactionsPage } from '@/pages/TransactionsPage'
import { PolicyRulesPage } from '@/pages/PolicyRulesPage'
import { UiPreferencesProvider } from '@/lib/ui/UiPreferencesProvider'

const backendClientMocks = vi.hoisted(() => ({
  createPolicyDocumentFromText: vi.fn(),
  createPolicyRule: vi.fn(),
  extractPolicyRules: vi.fn(),
  extractPolicyRulesFromDocument: vi.fn(),
  listPolicyRules: vi.fn(),
  resetPolicyData: vi.fn(),
  resetTransactions: vi.fn(),
  scanPolicy: vi.fn(),
  testDraftPolicyRule: vi.fn(),
  testPolicyRule: vi.fn(),
  updatePolicyRule: vi.fn(),
  uploadPolicyDocumentPdf: vi.fn(),
  enrichExistingTransactions: vi.fn(),
}))

const transactionSupabaseMocks = vi.hoisted(() => ({
  listRecentTransactions: vi.fn(),
}))

vi.mock('@/lib/api/backendClient', () => backendClientMocks)
vi.mock('@/lib/supabase/transactions', () => transactionSupabaseMocks)

function renderWithPreferences(component: React.ReactNode) {
  return render(
    <UiPreferencesProvider>
      <AssistantProvider>{component}</AssistantProvider>
    </UiPreferencesProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()

  backendClientMocks.enrichExistingTransactions.mockResolvedValue({
    total_seen: 0,
    updated: 0,
    skipped: 0,
    errors: 0,
    duration_ms: 0,
    batch_count: 0,
    error_messages: [],
  })
  backendClientMocks.resetTransactions.mockResolvedValue({
    deleted_transactions: 0,
    deleted_raw_transactions: 0,
    deleted_receipts: 0,
    deleted_preapprovals: 0,
    deleted_policy_checks: 0,
    deleted_violations: 0,
    deleted_risk_scores: 0,
    deleted_approval_requests: 0,
    deleted_expense_report_items: 0,
    deleted_expense_reports: 0,
  })
  backendClientMocks.listPolicyRules.mockResolvedValue([])
  backendClientMocks.resetPolicyData.mockResolvedValue({
    rows_deleted: {},
    storage_paths_removed: 0,
    warnings: [],
  })
  backendClientMocks.scanPolicy.mockResolvedValue({
    total_scanned: 0,
    compliant: 0,
    excluded_non_expense: 0,
    evidence_required: 0,
    approval_evidence_required: 0,
    approval_evidence_needed: 0,
    context_needed: 0,
    policy_violations: 0,
    policy_violation: 0,
    review_required: 0,
    high_or_critical: 0,
    individual_flags: 0,
    violations_created: 0,
    duration_ms: 0,
    batch_count: 0,
  })
  transactionSupabaseMocks.listRecentTransactions.mockResolvedValue([])

  Object.defineProperty(window, 'confirm', {
    configurable: true,
    value: vi.fn(() => true),
  })

  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      media: '',
      onchange: null,
    })),
  })
})

describe('destructive page actions', () => {
  it('routes the transactions reset button to the transactions reset API', async () => {
    renderWithPreferences(<TransactionsPage />)

    const button = await screen.findByRole('button', { name: 'Clear import' })
    fireEvent.click(button)

    await waitFor(() => expect(backendClientMocks.resetTransactions).toHaveBeenCalledTimes(1))
    expect(window.confirm).toHaveBeenCalledTimes(1)
  })

  it('routes the policy reset button to the policy reset API', async () => {
    renderWithPreferences(<PolicyRulesPage />)

    const button = await screen.findByRole('button', { name: 'Clear policy data' })
    fireEvent.click(button)

    await waitFor(() => expect(backendClientMocks.resetPolicyData).toHaveBeenCalledTimes(1))
    expect(window.confirm).toHaveBeenCalledTimes(1)
  })

  it('shows the simplified auto-activation flow for extracted policy rules', async () => {
    backendClientMocks.createPolicyDocumentFromText.mockResolvedValue({
      policy_document_id: 'doc_1',
      document: {
        id: 'doc_1',
        title: 'Expense policy',
        version: 'v1',
        source_type: 'pasted_text',
        file_name: null,
        storage_path: null,
        raw_text: 'Expenses over CAD 50 require manager preapproval before reimbursement.',
        extracted_text: 'Expenses over CAD 50 require manager preapproval before reimbursement.',
        extraction_status: 'extracted',
        extraction_error: null,
        active: true,
        synthetic: false,
        created_at: null,
        updated_at: null,
      },
      text_preview: 'Expenses over CAD 50 require manager preapproval before reimbursement.',
      char_count: 68,
    })
    backendClientMocks.extractPolicyRulesFromDocument.mockResolvedValue({
      policy_document_id: 'doc_1',
      extraction_run: null,
      draft_rules: [
        {
          id: 'rule_1',
          rule_code: 'PREAPPROVAL_OVER_50_DOC1',
          name: 'Preapproval over CAD 50',
          description: 'Manager preapproval is required over CAD 50.',
          severity: 'high',
          enabled: true,
          status: 'active',
          source_type: 'ai_extracted',
          source_text: 'Expenses over CAD 50 require manager preapproval before reimbursement.',
          rule_json: {},
          policy_document_id: 'doc_1',
          policy_extraction_run_id: 'run_1',
          extraction_confidence: 0.94,
          needs_human_review: false,
          validation_errors: [],
        },
        {
          id: 'rule_2',
          rule_code: 'GLOBAL_RECEIPT_RULE_DOC1',
          name: 'Receipt required everywhere',
          description: 'Receipt evidence is required for every expense.',
          severity: 'medium',
          enabled: false,
          status: 'draft',
          source_type: 'ai_extracted',
          source_text: 'Receipt evidence is required for every expense.',
          rule_json: {},
          policy_document_id: 'doc_1',
          policy_extraction_run_id: 'run_1',
          extraction_confidence: 0.81,
          needs_human_review: false,
          validation_errors: ['Activation blocked: global receipt rules need receipt evidence fields or category/merchant scope to avoid flooding compliance.'],
        },
      ],
      ambiguities: [],
      unsupported_or_missing_fields: [],
      suggested_feature_engineering: [],
      summary: 'Extracted two rules from the uploaded policy.',
    })

    renderWithPreferences(<PolicyRulesPage />)

    fireEvent.change(screen.getByLabelText('Policy text'), {
      target: { value: 'Expenses over CAD 50 require manager preapproval before reimbursement.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save text source' }))

    await waitFor(() => expect(backendClientMocks.createPolicyDocumentFromText).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: 'Extract draft rules' }))

    await screen.findByText('1 activated automatically')
    expect(screen.getByText('1 still need follow-up')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Accept recommended' })).toBeNull()
  })
})
