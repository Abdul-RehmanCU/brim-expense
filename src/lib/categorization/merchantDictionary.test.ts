import { describe, expect, it } from 'vitest'

import { categorizeTransaction } from '@/lib/categorization/transactionCategorization'
import { normalizeMerchantName } from '@/lib/normalization/transactionNormalization'
import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'

function transaction(overrides: Partial<NormalizedCsvTransaction> = {}): NormalizedCsvTransaction {
  return {
    transactionCode: '3001',
    description: 'INTUIT *QuickBooks TORONTO ON',
    sourceCategory: '0001',
    postingDate: '2025-09-03',
    transactionDate: '2025-09-02',
    merchantName: 'INTUIT *QuickBooks',
    normalizedMerchantName: normalizeMerchantName('INTUIT *QuickBooks') ?? 'INTUIT QUICKBOOKS',
    amountOriginal: 52.49,
    amountCad: 52.49,
    debitCredit: 'debit',
    merchantCategoryCode: '5734',
    merchantCity: 'TORONTO',
    merchantCountry: 'CAN',
    merchantPostalCode: null,
    merchantRegion: 'ON',
    conversionRate: null,
    ...overrides,
  }
}

describe('merchant dictionary categorization', () => {
  it('preserves merchant names for star-prefixed vendors with no numeric token', () => {
    expect(normalizeMerchantName('IN *WEATHERLOGICS INC. 204-3813708 MB')).toBe('IN WEATHERLOGICS INC. MB')
  })

  it('maps Intuit QuickBooks into Software / SaaS', () => {
    const result = categorizeTransaction(transaction())

    expect(result.category).toBe('Software / SaaS')
    expect(result.confidence).toBeGreaterThan(0.9)
  })

  it('maps Telus merchants into Telecom / Connectivity', () => {
    const result = categorizeTransaction(
      transaction({
        merchantName: 'TELUS ONLINE PAYMENT P',
        normalizedMerchantName: normalizeMerchantName('TELUS ONLINE PAYMENT P') ?? 'TELUS ONLINE PAYMENT P',
        description: 'TELUS ONLINE PAYMENT P EDMONTON AB',
        merchantCategoryCode: '4812',
      }),
    )

    expect(result.category).toBe('Telecom / Connectivity')
  })

  it('maps Weatherlogics even when normalized merchant is generic', () => {
    const result = categorizeTransaction(
      transaction({
        merchantName: 'IN *WEATHERLOGICS INC.',
        normalizedMerchantName: normalizeMerchantName('IN *WEATHERLOGICS INC. 204-3813708 MB') ?? 'IN INC.',
        description: 'IN *WEATHERLOGICS INC. 204-3813708 MB',
        merchantCategoryCode: '7392',
      }),
    )

    expect(result.category).toBe('Software / SaaS')
  })
})
