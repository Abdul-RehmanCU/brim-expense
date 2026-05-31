import { supabase } from '@/lib/supabase/client'
import type { ParsedImportTransaction } from '@/lib/import/csvParser'
import type { SyntheticAssignmentEmployee } from '@/lib/synthetic/assignment'
import type { Json } from '@/types/database'
import type { Transaction } from '@/types/domain'

export type ImportTransactionsResult = {
  insertedCount: number
  skippedDuplicateCount: number
  importBatchId: string
}

export type TransactionListItem = Transaction & {
  employeeName: string | null
  departmentName: string | null
  sourceFingerprint: string | null
}

const fingerprintLookupBatchSize = 250
const insertBatchSize = 500

function newImportBatchId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isString(value: string | null): value is string {
  return value !== null
}

function chunkArray<T>(items: T[], size: number) {
  const chunks: T[][] = []

  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size))
  }

  return chunks
}

export async function listSyntheticAssignmentEmployees(): Promise<SyntheticAssignmentEmployee[]> {
  const { data: employees, error: employeeError } = await supabase
    .from('employees')
    .select('id, department_id, full_name, email')
    .eq('synthetic', true)
    .order('full_name')

  if (employeeError) {
    throw new Error(employeeError.message)
  }

  const { data: departments, error: departmentError } = await supabase
    .from('departments')
    .select('id, name')
    .eq('synthetic', true)

  if (departmentError) {
    throw new Error(departmentError.message)
  }

  const departmentsById = new Map((departments ?? []).map((department) => [department.id, department.name]))

  return (employees ?? []).map((employee) => ({
    id: employee.id,
    departmentId: employee.department_id,
    fullName: employee.full_name,
    email: employee.email,
    departmentName: departmentsById.get(employee.department_id) ?? 'Synthetic Department',
  }))
}

export async function importParsedTransactions(
  parsedRows: ParsedImportTransaction[],
  sourceFileName: string | null,
): Promise<ImportTransactionsResult> {
  if (parsedRows.length === 0) {
    return { insertedCount: 0, skippedDuplicateCount: 0, importBatchId: newImportBatchId() }
  }

  const importBatchId = newImportBatchId()
  const fingerprints = parsedRows.map((row) => row.sourceFingerprint)
  const existingFingerprints = new Set<string>()

  for (const fingerprintBatch of chunkArray(fingerprints, fingerprintLookupBatchSize)) {
    const { data: existingRows, error: existingError } = await supabase
      .from('raw_transactions')
      .select('source_fingerprint')
      .in('source_fingerprint', fingerprintBatch)

    if (existingError) {
      throw new Error(existingError.message)
    }

    for (const row of existingRows ?? []) {
      existingFingerprints.add(row.source_fingerprint)
    }
  }

  const rowsToInsert = parsedRows.filter((row) => !existingFingerprints.has(row.sourceFingerprint))

  if (rowsToInsert.length === 0) {
    return {
      insertedCount: 0,
      skippedDuplicateCount: parsedRows.length,
      importBatchId,
    }
  }

  const rawIdByFingerprint = new Map<string, string>()

  for (const rowBatch of chunkArray(rowsToInsert, insertBatchSize)) {
    const { data: rawRows, error: rawError } = await supabase
      .from('raw_transactions')
      .insert(
        rowBatch.map((row) => ({
          source_file_name: sourceFileName,
          source_row_number: row.sourceRowNumber,
          source_fingerprint: row.sourceFingerprint,
          raw_payload: row.rawPayload as unknown as Json,
          import_batch_id: importBatchId,
          synthetic_context_assigned: Boolean(row.transaction.employeeId),
        })),
      )
      .select('id, source_fingerprint')

    if (rawError) {
      throw new Error(rawError.message)
    }

    for (const row of rawRows ?? []) {
      rawIdByFingerprint.set(row.source_fingerprint, row.id)
    }
  }

  for (const rowBatch of chunkArray(rowsToInsert, insertBatchSize)) {
    const { error: transactionError } = await supabase.from('transactions').insert(
      rowBatch.map((row) => ({
        raw_transaction_id: rawIdByFingerprint.get(row.sourceFingerprint) ?? null,
        employee_id: row.transaction.employeeId,
        department_id: row.transaction.departmentId,
        transaction_code: row.transaction.transactionCode,
        transaction_type: row.transaction.transactionType,
        transaction_eligibility: row.transaction.transactionEligibility,
        description: row.transaction.description,
        source_category: row.transaction.sourceCategory,
        network_category_code: row.transaction.networkCategoryCode,
        business_category: row.transaction.businessCategory,
        policy_category: row.transaction.policyCategory,
        category_source: row.transaction.categorySource,
        normalized_category: row.transaction.normalizedCategory,
        normalized_merchant_family: row.transaction.normalizedMerchantFamily,
        category_confidence: row.transaction.categoryConfidence,
        amount_bucket: row.transaction.amountBucket,
        posting_delay_days: row.transaction.postingDelayDays,
        is_account_activity: row.transaction.isAccountActivity,
        is_credit_or_refund: row.transaction.isCreditOrRefund,
        is_foreign_transaction: row.transaction.isForeignTransaction,
        posting_date: row.transaction.postingDate,
        transaction_date: row.transaction.transactionDate,
        merchant_name: row.transaction.merchantName,
        normalized_merchant_name: row.transaction.normalizedMerchantName,
        amount_original: row.transaction.amountOriginal,
        amount_cad: row.transaction.amountCad,
        debit_credit: row.transaction.debitCredit,
        merchant_category_code: row.transaction.merchantCategoryCode,
        merchant_city: row.transaction.merchantCity,
        merchant_country: row.transaction.merchantCountry,
        merchant_postal_code: row.transaction.merchantPostalCode,
        merchant_region: row.transaction.merchantRegion,
        conversion_rate: row.transaction.conversionRate,
        synthetic_assignment: Boolean(row.transaction.employeeId),
        business_purpose: null,
        guest_names: null,
      })),
    )

    if (transactionError) {
      throw new Error(transactionError.message)
    }
  }

  return {
    insertedCount: rowsToInsert.length,
    skippedDuplicateCount: parsedRows.length - rowsToInsert.length,
    importBatchId,
  }
}

export async function listRecentTransactions({ limit = 50, offset = 0 }: { limit?: number; offset?: number } = {}): Promise<TransactionListItem[]> {
  const { data: transactionRows, error: transactionError } = await supabase
    .from('transactions')
    .select('*')
    .order('transaction_date', { ascending: false, nullsFirst: false })
    .range(offset, offset + limit - 1)

  if (transactionError) {
    throw new Error(transactionError.message)
  }

  const transactions = transactionRows ?? []
  const employeeIds = [...new Set(transactions.map((transaction) => transaction.employee_id).filter(isString))]
  const departmentIds = [...new Set(transactions.map((transaction) => transaction.department_id).filter(isString))]
  const rawIds = [...new Set(transactions.map((transaction) => transaction.raw_transaction_id).filter(isString))]

  const [{ data: employees, error: employeeError }, { data: departments, error: departmentError }, { data: rawRows, error: rawError }] =
    await Promise.all([
      employeeIds.length > 0
        ? supabase.from('employees').select('id, full_name').in('id', employeeIds)
        : Promise.resolve({ data: [], error: null }),
      departmentIds.length > 0
        ? supabase.from('departments').select('id, name').in('id', departmentIds)
        : Promise.resolve({ data: [], error: null }),
      rawIds.length > 0
        ? supabase.from('raw_transactions').select('id, source_fingerprint').in('id', rawIds)
        : Promise.resolve({ data: [], error: null }),
    ])

  if (employeeError) {
    throw new Error(employeeError.message)
  }

  if (departmentError) {
    throw new Error(departmentError.message)
  }

  if (rawError) {
    throw new Error(rawError.message)
  }

  const employeeNameById = new Map((employees ?? []).map((employee) => [employee.id, employee.full_name]))
  const departmentNameById = new Map((departments ?? []).map((department) => [department.id, department.name]))
  const fingerprintByRawId = new Map((rawRows ?? []).map((rawRow) => [rawRow.id, rawRow.source_fingerprint]))

  return transactions.map((transaction) => ({
    id: transaction.id,
    rawTransactionId: transaction.raw_transaction_id,
    employeeId: transaction.employee_id,
    departmentId: transaction.department_id,
    transactionCode: transaction.transaction_code,
    description: transaction.description,
    sourceCategory: transaction.source_category,
    businessCategory: transaction.business_category ?? transaction.normalized_category,
    normalizedCategory: transaction.normalized_category,
    categoryConfidence: transaction.category_confidence,
    postingDate: transaction.posting_date,
    transactionDate: transaction.transaction_date,
    merchantName: transaction.merchant_name,
    normalizedMerchantName: transaction.normalized_merchant_name,
    amountOriginal: transaction.amount_original,
    amountCad: transaction.amount_cad,
    debitCredit: transaction.debit_credit,
    merchantCategoryCode: transaction.merchant_category_code,
    merchantCity: transaction.merchant_city,
    merchantCountry: transaction.merchant_country,
    merchantPostalCode: transaction.merchant_postal_code,
    merchantRegion: transaction.merchant_region,
    conversionRate: transaction.conversion_rate,
    syntheticAssignment: true,
    employeeName: transaction.employee_id ? employeeNameById.get(transaction.employee_id) ?? null : null,
    departmentName: transaction.department_id ? departmentNameById.get(transaction.department_id) ?? null : null,
    sourceFingerprint: transaction.raw_transaction_id
      ? fingerprintByRawId.get(transaction.raw_transaction_id) ?? null
      : null,
  }))
}
