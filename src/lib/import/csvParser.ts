import * as Papa from 'papaparse'

import { categorizeTransaction } from '@/lib/categorization/transactionCategorization'
import { findMissingColumns, requiredCsvColumns, type TransactionCsvRow } from '@/lib/import/csvColumns'
import { deriveImportedTransactionEnrichment } from '@/lib/import/transactionRouting'
import { normalizeCsvTransaction } from '@/lib/normalization/transactionNormalization'
import { assignSyntheticEmployee, type SyntheticAssignmentEmployee } from '@/lib/synthetic/assignment'
import { stableFingerprint } from '@/lib/utils/hash'

export type ParsedImportTransaction = {
  sourceRowNumber: number
  sourceFingerprint: string
  rawPayload: TransactionCsvRow
  transaction: {
    transactionCode: string | null
    description: string | null
    sourceCategory: string | null
    businessCategory: string
    normalizedCategory: string
    categoryConfidence: number
    categoryReason: string
    transactionType: string
    transactionEligibility: string
    networkCategoryCode: string | null
    policyCategory: string
    categorySource: string
    normalizedMerchantFamily: string | null
    amountBucket: string
    postingDelayDays: number | null
    isAccountActivity: boolean
    isCreditOrRefund: boolean
    isForeignTransaction: boolean
    postingDate: string | null
    transactionDate: string | null
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
    employeeId: string | null
    departmentId: string | null
    employeeName: string | null
    departmentName: string | null
  }
}

export type ImportRowError = {
  sourceRowNumber: number
  message: string
}

export type ParseImportResult = {
  rows: ParsedImportTransaction[]
  errors: ImportRowError[]
  missingColumns: string[]
}

type PapaRow = Record<string, string | undefined>

function toCsvRow(row: PapaRow): TransactionCsvRow {
  return requiredCsvColumns.reduce((accumulator, column) => {
    accumulator[column] = row[column]?.trim() ?? ''

    return accumulator
  }, {} as TransactionCsvRow)
}

export function parseTransactionCsv(
  contents: string,
  employees: SyntheticAssignmentEmployee[],
): ParseImportResult {
  const parsed = Papa.parse<PapaRow>(contents, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (header) => header.trim(),
  })

  const headers = parsed.meta.fields ?? []
  const missingColumns = findMissingColumns(headers)

  if (missingColumns.length > 0) {
    return { rows: [], errors: [], missingColumns }
  }

  const rows: ParsedImportTransaction[] = []
  const errors: ImportRowError[] = []

  parsed.data.forEach((rawRow, index) => {
    const sourceRowNumber = index + 2
    const rawPayload = toCsvRow(rawRow)
    const normalized = normalizeCsvTransaction(rawPayload)

    if (!normalized.transaction) {
      errors.push(
        ...normalized.errors.map((error) => ({
          sourceRowNumber,
          message: `${error.column}: ${error.message}`,
        })),
      )
      return
    }

    const categorized = categorizeTransaction(normalized.transaction)
    const enrichment = deriveImportedTransactionEnrichment(
      normalized.transaction,
      categorized.category,
      'deterministic_import_rule',
    )
    const assignment = assignSyntheticEmployee(
      {
        merchant: normalized.transaction.normalizedMerchantName,
        transactionDate: normalized.transaction.transactionDate,
        amountCad: normalized.transaction.amountCad,
        sourceRowNumber,
        transactionType: enrichment.transactionType,
        businessCategory: categorized.category,
      },
      employees,
    )
    const sourceFingerprint = stableFingerprint([
      rawPayload['Transaction Code'],
      rawPayload['Merchant Info DBA Name'],
      rawPayload['Transaction Date'],
      rawPayload['Transaction Amount'],
      rawPayload['Debit or Credit'],
      sourceRowNumber,
    ])

    rows.push({
      sourceRowNumber,
      sourceFingerprint,
      rawPayload,
      transaction: {
        ...normalized.transaction,
        businessCategory: categorized.category,
        normalizedCategory: categorized.category,
        categoryConfidence: categorized.confidence,
        categoryReason: categorized.reason,
        transactionType: enrichment.transactionType,
        transactionEligibility: enrichment.transactionEligibility,
        networkCategoryCode: enrichment.networkCategoryCode,
        policyCategory: enrichment.policyCategory,
        categorySource: enrichment.categorySource,
        normalizedMerchantFamily: enrichment.normalizedMerchantFamily,
        amountBucket: enrichment.amountBucket,
        postingDelayDays: enrichment.postingDelayDays,
        isAccountActivity: enrichment.isAccountActivity,
        isCreditOrRefund: enrichment.isCreditOrRefund,
        isForeignTransaction: enrichment.isForeignTransaction,
        employeeId: assignment?.id ?? null,
        departmentId: assignment?.departmentId ?? null,
        employeeName: assignment?.fullName ?? null,
        departmentName: assignment?.departmentName ?? null,
      },
    })
  })

  return {
    rows,
    errors,
    missingColumns,
  }
}
