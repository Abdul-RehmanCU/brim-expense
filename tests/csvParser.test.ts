import { describe, expect, it } from 'vitest'

import { parseTransactionCsv } from '@/lib/import/csvParser'
import type { SyntheticAssignmentEmployee } from '@/lib/synthetic/assignment'

const employees: SyntheticAssignmentEmployee[] = [
  {
    id: 'employee-1',
    departmentId: 'department-1',
    fullName: 'Sarah Chen',
    email: 'sarah.chen@brim-demo.example',
    departmentName: 'Marketing',
  },
]

describe('CSV parser', () => {
  it('parses tab-delimited Brim rows with required columns', () => {
    const csv = [
      'Transaction Code\tTransaction Description\tTransaction Category\tPosting date of transaction\tTransaction Date\tMerchant Info DBA Name\tTransaction Amount\tDebit or Credit\tMerchant Category Code\tMerchant City\tMerchant Country\tMerchant Postal Code\tMerchant State/Province\tConversion Rate',
      '3001\tFEDEX268575826 T1800 4633339 ON\t0001\t9/3/2025\t9/2/2025\tFEDEX268575826\t23.98\tDebit\t4215\tT1800 4633339\tCAN\tL4W 5K6\tON\t0',
    ].join('\n')

    const result = parseTransactionCsv(csv, employees)

    expect(result.missingColumns).toEqual([])
    expect(result.errors).toEqual([])
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0].transaction.normalizedMerchantName).toBe('FEDEX')
    expect(result.rows[0].transaction.businessCategory).toBe('Shipping / Courier')
    expect(result.rows[0].transaction.normalizedCategory).toBe('Shipping / Courier')
  })

  it('reports missing required columns before row normalization', () => {
    const result = parseTransactionCsv('Transaction Code\n3001', employees)

    expect(result.rows).toEqual([])
    expect(result.missingColumns).toContain('Transaction Amount')
  })
})
