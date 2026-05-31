import { describe, expect, it } from 'vitest'

import { categorizeTransaction } from '@/lib/categorization/transactionCategorization'
import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'

const transaction: NormalizedCsvTransaction = {
  transactionCode: '3001',
  description: 'CAT SCALE COMPANY 5632846263 IA',
  sourceCategory: '0001',
  postingDate: '2025-09-03',
  transactionDate: '2025-09-02',
  merchantName: 'CAT SCALE COMPANY',
  normalizedMerchantName: 'CAT SCALE COMPANY',
  amountOriginal: 20.89,
  amountCad: 28.86,
  debitCredit: 'debit',
  merchantCategoryCode: '5046',
  merchantCity: '5632846263',
  merchantCountry: 'USA',
  merchantPostalCode: '52773',
  merchantRegion: 'IA',
  conversionRate: 1.381694915,
}

describe('transaction categorization', () => {
  it('maps CAT SCALE COMPANY to fleet operations', () => {
    expect(categorizeTransaction(transaction).category).toBe('Transportation / Fleet / Operations')
  })

  it('maps FEDEX/MCC 4215 to shipping', () => {
    expect(
      categorizeTransaction({
        ...transaction,
        normalizedMerchantName: 'FEDEX',
        merchantCategoryCode: '4215',
      }).category,
    ).toBe('Shipping / Courier')
  })

  it('falls back with low confidence when no rule matches', () => {
    const result = categorizeTransaction({
      ...transaction,
      description: 'UNKNOWN MERCHANT PURCHASE',
      normalizedMerchantName: 'UNKNOWN MERCHANT',
      merchantCategoryCode: '9998',
    })

    expect(result.category).toBe('Uncategorized')
    expect(result.confidence).toBe(0.4)
  })

  it('maps obvious merchant names before broad fallback rules', () => {
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'UBER TRIP HELP.UBER.COM' }).category).toBe(
      'Ground Transportation',
    )
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'ENTERPRISE RENT-A-CAR' }).category).toBe(
      'Car / Truck Rental',
    )
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'MNDOT OSOW PERMIT' }).category).toBe(
      'Permits / Government Fees',
    )
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'PZG MT DEPT TRANSPORT' }).category).toBe(
      'Permits / Government Fees',
    )
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'AVETTA LLC' }).category).toBe(
      'Vendor / Compliance',
    )
    expect(categorizeTransaction({ ...transaction, normalizedMerchantName: 'TRUCKPARKINGCLUB' }).category).toBe(
      'Parking / Tolls',
    )
  })

  it('maps account activity and credits before merchant fallback rules', () => {
    expect(categorizeTransaction({ ...transaction, transactionCode: '0108', normalizedMerchantName: 'CWB EFT PAYMENT' }).category).toBe(
      'Account Payment / Transfer',
    )
    expect(categorizeTransaction({ ...transaction, transactionCode: '0375', normalizedMerchantName: '257018 POINT REDEMPTION' }).category).toBe(
      'Reward / Redemption',
    )
    expect(categorizeTransaction({ ...transaction, transactionCode: '3006', debitCredit: 'credit', normalizedMerchantName: 'LEROY SHELL' }).category).toBe(
      'Refund / Merchant Credit',
    )
  })
})
