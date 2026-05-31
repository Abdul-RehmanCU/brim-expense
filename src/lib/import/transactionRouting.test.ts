import { describe, expect, it } from 'vitest'

import { categorizeTransaction } from '@/lib/categorization/transactionCategorization'
import { deriveImportedTransactionEnrichment, resolveSourceTransactionRoute } from '@/lib/import/transactionRouting'
import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'

function transaction(overrides: Partial<NormalizedCsvTransaction> = {}): NormalizedCsvTransaction {
  return {
    transactionCode: '3001',
    description: "LOVE'S #0772 INSIDE PERRYTON TX",
    sourceCategory: '0001',
    postingDate: '2025-09-03',
    transactionDate: '2025-09-02',
    merchantName: "LOVE'S #0772 INSIDE",
    normalizedMerchantName: "LOVE'S INSIDE",
    amountOriginal: 100,
    amountCad: 137.65,
    debitCredit: 'debit',
    merchantCategoryCode: '5541',
    merchantCity: 'PERRYTON',
    merchantCountry: 'USA',
    merchantPostalCode: '79070',
    merchantRegion: 'TX',
    conversionRate: 1.3765,
    ...overrides,
  }
}

describe('source transaction routing', () => {
  it('routes account payments from zero-padded source codes', () => {
    const route = resolveSourceTransactionRoute(
      transaction({
        transactionCode: '0108',
        sourceCategory: '0019',
        debitCredit: 'credit',
      }),
    )

    expect(route?.transactionType).toBe('account_payment')
    expect(route?.transactionEligibility).toBe('excluded_non_expense')
  })

  it('forces reward redemption categorization for source combo credits', () => {
    const rewardTransaction = transaction({
      transactionCode: '0375',
      sourceCategory: '0001',
      debitCredit: 'credit',
      description: '257018 POINT REDEMPTION',
      merchantName: '257018 POINT REDEMPTION',
      normalizedMerchantName: '257018 POINT REDEMPTION',
    })

    const category = categorizeTransaction(rewardTransaction)
    const enrichment = deriveImportedTransactionEnrichment(rewardTransaction, category.category, 'deterministic_import_rule')

    expect(category.category).toBe('Reward / Redemption')
    expect(enrichment.transactionType).toBe('reward_redemption')
    expect(enrichment.policyCategory).toBe('Excluded Non-Expense')
    expect(enrichment.isAccountActivity).toBe(true)
  })

  it('excludes card program fees from reimbursement review', () => {
    const feeTransaction = transaction({
      transactionCode: '0137',
      sourceCategory: '0012',
      debitCredit: 'debit',
      description: 'AUTH USER FEE 2025-26',
      merchantName: 'AUTH USER FEE 2025-26',
      normalizedMerchantName: 'AUTH USER FEE 2025-26',
      merchantCategoryCode: '',
      conversionRate: 0,
    })

    const enrichment = deriveImportedTransactionEnrichment(feeTransaction, 'Uncategorized', 'fallback')

    expect(enrichment.transactionType).toBe('card_fee')
    expect(enrichment.transactionEligibility).toBe('excluded_non_expense')
    expect(enrichment.policyCategory).toBe('Excluded Non-Expense')
    expect(enrichment.isAccountActivity).toBe(true)
  })

  it('excludes cash advance fees while leaving actual cash advances routable', () => {
    const feeRoute = resolveSourceTransactionRoute(
      transaction({
        transactionCode: '0401',
        sourceCategory: '0010',
        debitCredit: 'debit',
      }),
    )
    const cashRoute = resolveSourceTransactionRoute(
      transaction({
        transactionCode: '3005',
        sourceCategory: '0003',
        debitCredit: 'debit',
      }),
    )

    expect(feeRoute?.transactionType).toBe('cash_advance_fee')
    expect(feeRoute?.transactionEligibility).toBe('excluded_non_expense')
    expect(cashRoute?.transactionType).toBe('cash_advance')
    expect(cashRoute?.transactionEligibility).toBe('finance_review')
  })
})
