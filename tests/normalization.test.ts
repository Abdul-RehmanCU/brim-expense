import { describe, expect, it } from 'vitest'

import { normalizeCsvTransaction, normalizeMerchantName, parseBrimDate } from '@/lib/normalization/transactionNormalization'
import type { TransactionCsvRow } from '@/lib/import/csvColumns'

const baseRow: TransactionCsvRow = {
  'Transaction Code': '3001',
  'Transaction Description': 'FEDEX268575826 T1800 4633339 ON',
  'Transaction Category': '0001',
  'Posting date of transaction': '9/3/2025',
  'Transaction Date': '9/2/2025',
  'Merchant Info DBA Name': 'FEDEX268575826',
  'Transaction Amount': '23.98',
  'Debit or Credit': 'Debit',
  'Merchant Category Code': '4215',
  'Merchant City': 'T1800 4633339',
  'Merchant Country': 'CAN',
  'Merchant Postal Code': 'L4W 5K6',
  'Merchant State/Province': 'ON',
  'Conversion Rate': '0',
}

describe('transaction normalization', () => {
  it('parses Brim M/D/YYYY dates to ISO dates', () => {
    expect(parseBrimDate('9/2/2025')).toBe('2025-09-02')
    expect(parseBrimDate('13/2/2025')).toBeNull()
  })

  it('keeps zero conversion-rate rows in original CAD amount', () => {
    const result = normalizeCsvTransaction(baseRow)

    expect(result.transaction?.amountOriginal).toBe(23.98)
    expect(result.transaction?.amountCad).toBe(23.98)
    expect(result.transaction?.conversionRate).toBeNull()
  })

  it('multiplies by row-level conversion rate for non-CAD rows', () => {
    const result = normalizeCsvTransaction({
      ...baseRow,
      'Merchant Country': 'USA',
      'Transaction Amount': '20.89',
      'Conversion Rate': '1.381694915',
    })

    expect(result.transaction?.amountCad).toBe(28.86)
    expect(result.transaction?.conversionRate).toBe(1.381694915)
  })

  it('normalizes long merchant fragments conservatively', () => {
    expect(normalizeMerchantName('FEDEX268575826')).toBe('FEDEX')
    expect(normalizeMerchantName('CAT SCALE COMPANY')).toBe('CAT SCALE COMPANY')
    expect(normalizeMerchantName('Amazon.ca*BF6C21X53')).toBe('AMAZON.CA')
  })
})
