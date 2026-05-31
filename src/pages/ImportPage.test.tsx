// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ImportPage } from '@/pages/ImportPage'

const backendMocks = vi.hoisted(() => ({
  importTransactions: vi.fn(),
  validateTransactionDataQuality: vi.fn(),
}))

const supabaseMocks = vi.hoisted(() => ({
  listSyntheticAssignmentEmployees: vi.fn(),
}))

const parserMocks = vi.hoisted(() => ({
  parseTransactionCsv: vi.fn(),
}))

vi.mock('@/components/layout/PageScaffold', () => ({
  PageScaffold: ({ children, title, description }: { children: ReactNode; title: string; description?: string }) => (
    <div>
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
      {children}
    </div>
  ),
}))

vi.mock('@/lib/api/backendClient', () => backendMocks)
vi.mock('@/lib/assistant/AssistantProvider', () => ({
  useAssistantPageContext: vi.fn(),
}))
vi.mock('@/lib/supabase/transactions', () => supabaseMocks)
vi.mock('@/lib/import/csvParser', () => parserMocks)

vi.mock('@/lib/ui/preferences', () => ({
  useUiPreferences: () => ({
    locale: 'en-CA',
    t: (key: string) => {
      const copy: Record<string, string> = {
        'import.eyebrow': 'Import',
        'import.title': 'Import',
        'import.description': 'Upload a card export, preview the cleanup, then import it into your workspace.',
        'import.chooseCsv': 'Choose CSV file',
        'import.dataSourceHint': 'Comma or tab-delimited data',
        'import.csvText': 'CSV text',
        'import.placeholder': 'Paste CSV or TSV rows here',
        'actions.import': 'Import',
        'import.statusTitle': 'Import status',
        'import.rowsReady': 'Rows ready',
        'import.rowErrors': 'Row errors',
        'import.missingColumns': 'Missing columns',
        'import.importComplete': 'Import complete',
        'import.inserted': 'Inserted',
        'import.transactions': 'transactions.',
        'import.skipped': 'Skipped',
        'import.errorsTitle': 'Row errors',
        'import.previewTitle': 'Preview',
        'import.previewBody': 'Check the cleaned-up rows before you bring them in.',
        'import.previewRowsLabel': 'Preview rows',
        'import.readinessLabel': 'Import readiness',
        'import.readinessNeedsAttention': 'Needs attention',
        'import.readinessReady': 'Ready',
        'import.row': 'Row',
        'import.date': 'Date',
        'import.merchant': 'Merchant',
        'import.category': 'Category',
        'import.amountCad': 'Amount CAD',
        'import.syntheticEmployee': 'Assigned employee',
        'import.fingerprint': 'Fingerprint',
        'import.unassigned': 'Unassigned',
        'import.sourceLabel': 'Source',
        'import.sourcePasted': 'Pasted CSV text',
        'transactions.syntheticDepartment': 'Synthetic Department',
      }

      return copy[key] ?? key
    },
  }),
}))

describe('ImportPage', () => {
  beforeEach(() => {
    backendMocks.importTransactions.mockReset()
    backendMocks.validateTransactionDataQuality.mockReset()
    supabaseMocks.listSyntheticAssignmentEmployees.mockReset()
    parserMocks.parseTransactionCsv.mockReset()
  })

  it('uses backend validation for preview and backend import for persistence', async () => {
    supabaseMocks.listSyntheticAssignmentEmployees.mockResolvedValue([
      {
        id: 'emp-1',
        departmentId: 'dept-1',
        fullName: 'Sarah Chen',
        email: 'sarah@example.com',
        departmentName: 'Operations',
      },
    ])
    parserMocks.parseTransactionCsv.mockReturnValue({
      rows: [
        {
          sourceRowNumber: 2,
          sourceFingerprint: 'fp-1',
          rawPayload: { 'Transaction Date': '2026-05-10' },
          transaction: {
            transactionCode: '3001',
            description: 'MNDOT OSOW PERMITS FEE ATLANTA GA',
            sourceCategory: 'Fuel',
            businessCategory: 'Fuel',
            normalizedCategory: 'Fuel',
            categoryConfidence: 0.42,
            categoryReason: 'merchant rule',
            transactionType: 'expense',
            transactionEligibility: 'eligible_expense',
            networkCategoryCode: '3001',
            policyCategory: 'Fuel',
            categorySource: 'fallback',
            normalizedMerchantFamily: 'MNDOT',
            amountBucket: '50_to_499',
            postingDelayDays: 2,
            isAccountActivity: false,
            isCreditOrRefund: false,
            isForeignTransaction: true,
            postingDate: '2026-05-12',
            transactionDate: '2026-05-10',
            merchantName: 'MNDOT OSOW PERMITS FEE',
            normalizedMerchantName: 'MNDOT OSOW PERMITS FEE',
            amountOriginal: 227.9,
            amountCad: 227.9,
            debitCredit: 'debit',
            merchantCategoryCode: '5542',
            merchantCity: 'Atlanta',
            merchantCountry: 'USA',
            merchantPostalCode: null,
            merchantRegion: 'GA',
            conversionRate: 1,
            employeeId: 'emp-1',
            departmentId: 'dept-1',
            employeeName: 'Sarah Chen',
            departmentName: 'Operations',
          },
        },
      ],
      errors: [],
      missingColumns: [],
    })

    const validationResponse = {
      row_count: 1,
      findings: [],
      summary: {
        row_count: 1,
        finding_count: 0,
        critical_count: 0,
        high_count: 0,
        medium_count: 0,
        low_count: 0,
        rows_with_findings: 0,
      },
      great_expectations: {
        available: false,
        suite_name: 'brim_transaction_data_quality',
        evaluated_expectations: 0,
        failed_expectations: 0,
        error: null,
      },
    }

    backendMocks.validateTransactionDataQuality.mockResolvedValue(validationResponse)
    backendMocks.importTransactions.mockResolvedValue({
      inserted_count: 1,
      skipped_duplicate_count: 0,
      import_batch_id: 'batch-1',
      validation: validationResponse,
      persisted: true,
      authoritative_enrichment_applied: 1,
      warnings: [],
    })

    renderWithAssistant(<ImportPage />)

    fireEvent.change(screen.getByPlaceholderText('Paste CSV or TSV rows here'), {
      target: { value: 'csv rows' },
    })
    await waitFor(() => expect(backendMocks.validateTransactionDataQuality).toHaveBeenCalledTimes(1))
    expect(backendMocks.validateTransactionDataQuality).toHaveBeenCalledWith({
      rows: [
        expect.objectContaining({
          source_row_number: 2,
          source_fingerprint: 'fp-1',
          amount_cad: 227.9,
          employee_id: 'emp-1',
        }),
      ],
      run_great_expectations: false,
    })

    fireEvent.click(screen.getByRole('button', { name: 'Import' }))

    await waitFor(() => expect(backendMocks.importTransactions).toHaveBeenCalledTimes(1))
    expect(backendMocks.importTransactions).toHaveBeenCalledWith({
      source_file_name: null,
      rows: [
        expect.objectContaining({
          source_row_number: 2,
          source_fingerprint: 'fp-1',
        }),
      ],
      run_data_quality: true,
      run_great_expectations: false,
    })

    expect(await screen.findByText('Import complete')).toBeTruthy()
    expect(screen.getByText('Import readiness: Ready')).toBeTruthy()
  })
})

function renderWithAssistant(node: ReactNode) {
  return render(node)
}
