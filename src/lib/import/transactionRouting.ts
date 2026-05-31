import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'
import { findMerchantDictionaryMatch } from '@/lib/categorization/merchantDictionary'

export type SourceTransactionRoute = {
  transactionType:
    | 'expense'
    | 'merchant_credit'
    | 'card_fee'
    | 'cash_advance'
    | 'cash_advance_fee'
    | 'cash_advance_interest'
    | 'account_payment'
    | 'reward_redemption'
    | 'cash_advance_reversal'
  transactionEligibility: 'eligible_expense' | 'excluded_non_expense' | 'finance_review'
  forcedCategory: string | null
  categorySource: string
  isAccountActivity: boolean
  isCreditOrRefund: boolean
}

type RouteKey =
  | '3001|1|debit'
  | '3006|1|credit'
  | '137|12|debit'
  | '3005|3|debit'
  | '401|10|debit'
  | '404|2|debit'
  | '108|19|credit'
  | '375|1|credit'
  | '3035|3|credit'

const SOURCE_TRANSACTION_ROUTES: Record<RouteKey, SourceTransactionRoute> = {
  '3001|1|debit': {
    transactionType: 'expense',
    transactionEligibility: 'eligible_expense',
    forcedCategory: null,
    categorySource: 'source_combo_purchase_rail',
    isAccountActivity: false,
    isCreditOrRefund: false,
  },
  '3006|1|credit': {
    transactionType: 'merchant_credit',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Refund / Merchant Credit',
    categorySource: 'source_combo_merchant_credit',
    isAccountActivity: false,
    isCreditOrRefund: true,
  },
  '137|12|debit': {
    transactionType: 'card_fee',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Card Fees / Interest',
    categorySource: 'source_combo_card_fee',
    isAccountActivity: true,
    isCreditOrRefund: false,
  },
  '3005|3|debit': {
    transactionType: 'cash_advance',
    transactionEligibility: 'finance_review',
    forcedCategory: 'Cash Advance / ATM Withdrawal',
    categorySource: 'source_combo_cash_advance',
    isAccountActivity: false,
    isCreditOrRefund: false,
  },
  '401|10|debit': {
    transactionType: 'cash_advance_fee',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Cash Advance Fee',
    categorySource: 'source_combo_cash_advance_fee',
    isAccountActivity: true,
    isCreditOrRefund: false,
  },
  '404|2|debit': {
    transactionType: 'cash_advance_interest',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Cash Advance Interest',
    categorySource: 'source_combo_cash_advance_interest',
    isAccountActivity: true,
    isCreditOrRefund: false,
  },
  '108|19|credit': {
    transactionType: 'account_payment',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Account Payment / Transfer',
    categorySource: 'source_combo_account_payment',
    isAccountActivity: true,
    isCreditOrRefund: true,
  },
  '375|1|credit': {
    transactionType: 'reward_redemption',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Reward / Redemption',
    categorySource: 'source_combo_reward_redemption',
    isAccountActivity: true,
    isCreditOrRefund: true,
  },
  '3035|3|credit': {
    transactionType: 'cash_advance_reversal',
    transactionEligibility: 'excluded_non_expense',
    forcedCategory: 'Cash Advance Reversal / Adjustment',
    categorySource: 'source_combo_cash_advance_reversal',
    isAccountActivity: false,
    isCreditOrRefund: true,
  },
}

function canonicalCode(value: string | null | undefined) {
  const trimmed = value?.trim() ?? ''

  if (!trimmed) {
    return null
  }

  if (/^\d+$/.test(trimmed)) {
    const normalized = String(Number.parseInt(trimmed, 10))
    return normalized === 'NaN' ? trimmed : normalized
  }

  return trimmed.toUpperCase()
}

function parseIsoDate(value: string | null | undefined) {
  if (!value) {
    return null
  }

  const date = new Date(`${value}T00:00:00.000Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

function postingDelayDays(transactionDate: string | null, postingDate: string | null) {
  const transaction = parseIsoDate(transactionDate)
  const posting = parseIsoDate(postingDate)

  if (!transaction || !posting) {
    return null
  }

  return Math.round((posting.getTime() - transaction.getTime()) / 86_400_000)
}

function normalizedMerchantFamily(transaction: NormalizedCsvTransaction) {
  const dictionaryMatch = findMerchantDictionaryMatch(transaction)

  if (dictionaryMatch) {
    return dictionaryMatch.merchantFamily
  }

  const merchant = (transaction.normalizedMerchantName ?? transaction.merchantName ?? '').trim().toUpperCase()

  if (!merchant) {
    return null
  }

  if (merchant.includes('POINT REDEMPTION')) {
    return 'POINT REDEMPTION'
  }

  if (merchant.includes('CWB EFT PAYMENT')) {
    return 'CWB EFT PAYMENT'
  }

  return merchant
    .replace(/^[0-9]+\s+/, '')
    .replace(/\b[0-9]{2,}\b/g, ' ')
    .replace(/\*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function amountBucket(amountCad: number, isCredit: boolean) {
  if (isCredit) {
    return 'credit'
  }
  if (amountCad < 50) {
    return 'under_50'
  }
  if (amountCad < 500) {
    return '50_to_499'
  }
  if (amountCad < 1000) {
    return '500_to_999'
  }
  return '1000_plus'
}

function isForeignTransaction(country: string | null) {
  const normalized = (country ?? '').trim().toUpperCase()
  return normalized.length > 0 && !['CA', 'CAN', 'CANADA'].includes(normalized)
}

export function resolveSourceTransactionRoute(transaction: Pick<NormalizedCsvTransaction, 'transactionCode' | 'sourceCategory' | 'debitCredit'>) {
  const transactionCode = canonicalCode(transaction.transactionCode)
  const sourceCategory = canonicalCode(transaction.sourceCategory)
  const direction = transaction.debitCredit.trim().toLowerCase()
  const routeKey = [transactionCode, sourceCategory, direction].join('|') as RouteKey

  return SOURCE_TRANSACTION_ROUTES[routeKey] ?? null
}

export function deriveImportedTransactionEnrichment(
  transaction: NormalizedCsvTransaction,
  businessCategory: string,
  categorySource: string,
) {
  const route = resolveSourceTransactionRoute(transaction)
  const eligibility = route?.transactionEligibility ?? 'eligible_expense'
  const policyCategory =
    eligibility === 'excluded_non_expense'
      ? 'Excluded Non-Expense'
      : eligibility === 'finance_review'
        ? 'Finance Review'
        : businessCategory

  return {
    transactionType: route?.transactionType ?? 'expense',
    transactionEligibility: eligibility,
    networkCategoryCode: canonicalCode(transaction.transactionCode) ?? canonicalCode(transaction.merchantCategoryCode),
    policyCategory,
    categorySource: route?.forcedCategory ? route.categorySource : categorySource,
    normalizedMerchantFamily: normalizedMerchantFamily(transaction),
    amountBucket: amountBucket(transaction.amountCad, route?.isCreditOrRefund ?? transaction.debitCredit === 'credit'),
    postingDelayDays: postingDelayDays(transaction.transactionDate, transaction.postingDate),
    isAccountActivity: route?.isAccountActivity ?? false,
    isCreditOrRefund: route?.isCreditOrRefund ?? transaction.debitCredit === 'credit',
    isForeignTransaction: isForeignTransaction(transaction.merchantCountry),
  }
}
