import type { RequiredCsvColumn, TransactionCsvRow } from '@/lib/import/csvColumns'

export type NormalizedCsvTransaction = {
  transactionCode: string | null
  description: string | null
  sourceCategory: string | null
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
}

export type RowNormalizationError = {
  column: RequiredCsvColumn
  message: string
}

const longNumberPattern = /\b\d{5,}\b/g
const phonePattern = /\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b/g

function emptyToNull(value: string | undefined) {
  const trimmed = value?.trim() ?? ''

  return trimmed.length > 0 ? trimmed : null
}

export function parseMoney(value: string) {
  const normalized = value.replace(/[$,]/g, '').trim()
  const parsed = Number(normalized)

  return Number.isFinite(parsed) ? parsed : null
}

export function parseConversionRate(value: string) {
  const parsed = Number(value.trim())

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null
  }

  return parsed
}

export function parseBrimDate(value: string) {
  const trimmed = value.trim()
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(trimmed)

  if (!match) {
    return null
  }

  const month = Number(match[1])
  const day = Number(match[2])
  const year = Number(match[3])
  const date = new Date(Date.UTC(year, month - 1, day))

  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null
  }

  return `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day
    .toString()
    .padStart(2, '0')}`
}

export function normalizeMerchantName(value: string) {
  const upper = value.trim().toUpperCase()

  if (!upper) {
    return null
  }

  return upper
    .replace(/\*[A-Z]*\d+[A-Z0-9]*/g, '')
    .replace(phonePattern, '')
    .replace(longNumberPattern, '')
    .replace(/([A-Z])\d{5,}/g, '$1')
    .replace(/[#*]+/g, ' ')
    .replace(/[^A-Z0-9&'./ -]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function normalizeCsvTransaction(row: TransactionCsvRow) {
  const errors: RowNormalizationError[] = []
  const amountOriginal = parseMoney(row['Transaction Amount'])

  if (amountOriginal === null) {
    errors.push({
      column: 'Transaction Amount',
      message: `Invalid amount "${row['Transaction Amount']}".`,
    })
  }

  const debitCreditValue = row['Debit or Credit'].trim().toLowerCase()
  const debitCredit =
    debitCreditValue === 'debit' || debitCreditValue === 'credit' ? debitCreditValue : null

  if (debitCredit === null) {
    errors.push({
      column: 'Debit or Credit',
      message: `Expected Debit or Credit, received "${row['Debit or Credit']}".`,
    })
  }

  const postingDate = parseBrimDate(row['Posting date of transaction'])
  const transactionDate = parseBrimDate(row['Transaction Date'])

  if (!postingDate) {
    errors.push({
      column: 'Posting date of transaction',
      message: `Invalid posting date "${row['Posting date of transaction']}".`,
    })
  }

  if (!transactionDate) {
    errors.push({
      column: 'Transaction Date',
      message: `Invalid transaction date "${row['Transaction Date']}".`,
    })
  }

  if (errors.length > 0 || amountOriginal === null || debitCredit === null) {
    return { transaction: null, errors }
  }

  const conversionRate = parseConversionRate(row['Conversion Rate'])
  const amountCad = Number((amountOriginal * (conversionRate ?? 1)).toFixed(2))

  return {
    transaction: {
      transactionCode: emptyToNull(row['Transaction Code']),
      description: emptyToNull(row['Transaction Description']),
      sourceCategory: emptyToNull(row['Transaction Category']),
      postingDate,
      transactionDate,
      merchantName: emptyToNull(row['Merchant Info DBA Name']),
      normalizedMerchantName: normalizeMerchantName(row['Merchant Info DBA Name']),
      amountOriginal,
      amountCad,
      debitCredit,
      merchantCategoryCode: emptyToNull(row['Merchant Category Code']),
      merchantCity: emptyToNull(row['Merchant City']),
      merchantCountry: emptyToNull(row['Merchant Country']),
      merchantPostalCode: emptyToNull(row['Merchant Postal Code']),
      merchantRegion: emptyToNull(row['Merchant State/Province']),
      conversionRate,
    } satisfies NormalizedCsvTransaction,
    errors,
  }
}
