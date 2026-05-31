import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'
import { findMerchantDictionaryMatch } from '@/lib/categorization/merchantDictionary'
import { resolveSourceTransactionRoute } from '@/lib/import/transactionRouting'

export type CategorizationResult = {
  category: string
  confidence: number
  reason: string
}

type CategoryRule = {
  category: string
  confidence: number
  keywords?: string[]
  mcc?: string[]
  reason: string
}

const rules: CategoryRule[] = [
  {
    category: 'Shipping / Courier',
    confidence: 0.95,
    keywords: ['FEDEX', 'UPS', 'DHL'],
    mcc: ['4215'],
    reason: 'Matched courier merchant or MCC.',
  },
  {
    category: 'Ground Transportation',
    confidence: 0.95,
    keywords: ['UBER', 'LYFT', 'TAXI'],
    reason: 'Matched rideshare, taxi, or ground transportation merchant.',
  },
  {
    category: 'Car / Truck Rental',
    confidence: 0.95,
    keywords: ['ENTERPRISE', 'NATIONAL CAR', 'HERTZ', 'AVIS', 'BUDGET RENT A CAR'],
    mcc: ['3405', '3357', '3389', '3393', '7512'],
    reason: 'Matched car rental merchant or MCC.',
  },
  {
    category: 'Permits / Government Fees',
    confidence: 0.92,
    keywords: [
      'MNDOT',
      'UDOT',
      'TDOT',
      'TXDMV',
      'KYTC',
      'NDHP',
      'MCSD',
      'DOT',
      'DMV',
      'DEPT OF TRANS',
      'DEPT TRANSPORT',
      'DEPARTMENT OF TRANS',
      'OSOW',
      'PERMIT',
      'HAULING PERMITS',
      'MOTOR CARRIER',
      'MOTOR CARRIERS',
    ],
    mcc: ['9399'],
    reason: 'Matched permit or government transportation fee pattern.',
  },
  {
    category: 'Vendor / Compliance',
    confidence: 0.9,
    keywords: ['AVETTA'],
    reason: 'Matched vendor compliance merchant.',
  },
  {
    category: 'Fuel',
    confidence: 0.95,
    keywords: [
      'GAS',
      'SHELL',
      'ESSO',
      'PETRO',
      'CHEVRON',
      'KWIK TRIP',
      'CIRCLE K',
      'EXXON',
      'PILOT',
      'FLYING J',
      "LOVE'S",
      'CENEX',
      'MARATHON',
      'ARCO',
      'TA ',
      'ONE9',
      'TRUCKSTOP',
    ],
    mcc: ['5541', '5542'],
    reason: 'Matched fuel merchant or MCC.',
  },
  {
    category: 'Parking / Tolls',
    confidence: 0.88,
    keywords: ['PARKING', 'TOLL', 'A30 EXPRESS', 'CROSSING', 'TRUCKPARKINGCLUB'],
    mcc: ['4784', '4789'],
    reason: 'Matched parking, toll, or crossing pattern.',
  },
  {
    category: 'Lodging',
    confidence: 0.92,
    keywords: ['HOTEL', 'MOTEL', 'INN', 'WYNDHAM', 'SUPER 8', 'BEST WEST', 'LA QUINTA', 'SLEEP INN', 'LODGING'],
    mcc: ['3502', '3516', '3631', '3709', '3722', '7011'],
    reason: 'Matched lodging merchant or MCC.',
  },
  {
    category: 'Meals / Entertainment',
    confidence: 0.85,
    keywords: ['RESTAURANT', 'CAFE', 'COFFEE', 'SKIPTHEDISHES', 'FOOD', 'BAR'],
    mcc: ['5812', '5813', '5814'],
    reason: 'Matched meal or entertainment pattern.',
  },
  {
    category: 'Office Supplies',
    confidence: 0.85,
    keywords: ['STAPLES', 'OFFICE', 'AMAZON', 'AMZN', 'COSTCO', 'HOME DEPOT'],
    mcc: ['5300', '5200', '5943'],
    reason: 'Matched office, supplies, or general procurement pattern.',
  },
  {
    category: 'Software / SaaS',
    confidence: 0.9,
    keywords: ['ADOBE', 'MICROSOFT', 'GOOGLE', 'OPENAI', 'SLACK', 'NOTION', 'GITHUB', 'SYLECTUS', 'SIRIUSXM'],
    mcc: ['5817', '5818', '4899'],
    reason: 'Matched software or subscription merchant/MCC.',
  },
  {
    category: 'Vehicle Maintenance',
    confidence: 0.9,
    keywords: ['TIRE', 'TRUCK LUBE', 'CARWASH', 'CARWASH', 'AUTO', 'KUBOTA', 'TRAILERS', 'PNEUMATIC', 'MICHELIN'],
    mcc: ['5013', '5532', '5533', '5561', '7531', '7538', '7542'],
    reason: 'Matched vehicle maintenance merchant or MCC.',
  },
  {
    category: 'Transportation / Fleet / Operations',
    confidence: 0.95,
    keywords: ['CAT SCALE COMPANY', 'SCALE', 'WEIGH STATION', 'SUPERLOAD', 'TRUCK'],
    mcc: ['5046', '5085', '8220'],
    reason: 'Matched fleet operations merchant or MCC.',
  },
  {
    category: 'Alcohol / Restricted',
    confidence: 0.95,
    keywords: ['LCBO', 'SAQ', 'LIQUOR', 'BEER', 'WINE'],
    reason: 'Matched restricted alcohol keyword.',
  },
  {
    category: 'Non-Reimbursable Fine',
    confidence: 0.9,
    keywords: ['TICKET', 'FINE', 'VIOLATION'],
    reason: 'Matched fine or ticket keyword.',
  },
]

export function categorizeTransaction(transaction: NormalizedCsvTransaction): CategorizationResult {
  const sourceRoute = resolveSourceTransactionRoute(transaction)

  if (sourceRoute?.forcedCategory) {
    return {
      category: sourceRoute.forcedCategory,
      confidence: 0.99,
      reason: `Matched source-specific combo route ${sourceRoute.categorySource}.`,
    }
  }

  const searchable = [
    transaction.normalizedMerchantName,
    transaction.description?.toUpperCase(),
    transaction.sourceCategory?.toUpperCase(),
  ]
    .filter(Boolean)
    .join(' ')
  const mcc = transaction.merchantCategoryCode?.trim()
  const transactionCode = transaction.transactionCode?.trim()

  if (searchable.includes('CWB EFT PAYMENT') || transactionCode === '0108') {
    return {
      category: 'Account Payment / Transfer',
      confidence: 0.98,
      reason: 'Matched account payment or transfer activity.',
    }
  }

  if (searchable.includes('POINT REDEMPTION') || transactionCode === '0375') {
    return {
      category: 'Reward / Redemption',
      confidence: 0.98,
      reason: 'Matched reward redemption activity.',
    }
  }

  if (transaction.debitCredit === 'credit' || transactionCode === '3006') {
    return {
      category: 'Refund / Merchant Credit',
      confidence: 0.95,
      reason: 'Matched credit or merchant refund activity.',
    }
  }

  const merchantDictionaryMatch = findMerchantDictionaryMatch(transaction)

  if (merchantDictionaryMatch) {
    return {
      category: merchantDictionaryMatch.category,
      confidence: merchantDictionaryMatch.confidence,
      reason: merchantDictionaryMatch.reason,
    }
  }

  for (const rule of rules) {
    const keywordMatched = rule.keywords?.some((keyword) => searchable.includes(keyword)) ?? false
    const mccMatched = mcc ? rule.mcc?.includes(mcc) ?? false : false

    if (keywordMatched || mccMatched) {
      return rule
    }
  }

  return {
    category: 'Uncategorized',
    confidence: 0.4,
    reason: 'No deterministic category rule matched.',
  }
}
