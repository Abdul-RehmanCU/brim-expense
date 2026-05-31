import type { NormalizedCsvTransaction } from '@/lib/normalization/transactionNormalization'

export type MerchantDictionaryMatch = {
  canonicalName: string
  merchantFamily: string
  category: string
  confidence: number
  reason: string
}

type MerchantDictionaryRule = {
  canonicalName: string
  merchantFamily: string
  category: string
  confidence: number
  exactNormalizedNames?: string[]
  keywords?: string[]
  reason: string
}

const merchantDictionaryRules: MerchantDictionaryRule[] = [
  {
    canonicalName: 'INTUIT QUICKBOOKS',
    merchantFamily: 'INTUIT',
    category: 'Software / SaaS',
    confidence: 0.96,
    exactNormalizedNames: ['INTUIT'],
    keywords: ['QUICKBOOKS'],
    reason: 'Matched Intuit / QuickBooks finance software merchant.',
  },
  {
    canonicalName: 'WEATHERLOGICS',
    merchantFamily: 'WEATHERLOGICS',
    category: 'Software / SaaS',
    confidence: 0.93,
    keywords: ['WEATHERLOGICS'],
    reason: 'Matched weather intelligence software vendor.',
  },
  {
    canonicalName: 'BAMBOOHR',
    merchantFamily: 'BAMBOOHR',
    category: 'Software / SaaS',
    confidence: 0.96,
    exactNormalizedNames: ['BAMBOOHRLLC'],
    keywords: ['BAMBOOHR'],
    reason: 'Matched HR software merchant.',
  },
  {
    canonicalName: 'RIGHT NETWORKS',
    merchantFamily: 'RIGHT NETWORKS',
    category: 'Software / SaaS',
    confidence: 0.95,
    exactNormalizedNames: ['RIGHT NETWORKS'],
    keywords: ['RIGHT NETWORKS'],
    reason: 'Matched hosted accounting and application platform provider.',
  },
  {
    canonicalName: 'HOSTPAPA',
    merchantFamily: 'HOSTPAPA',
    category: 'Software / SaaS',
    confidence: 0.95,
    keywords: ['HOSTPAPA'],
    reason: 'Matched web hosting provider.',
  },
  {
    canonicalName: 'GODADDY',
    merchantFamily: 'GODADDY',
    category: 'Software / SaaS',
    confidence: 0.95,
    keywords: ['GODADDY'],
    reason: 'Matched domain and web-services provider.',
  },
  {
    canonicalName: 'BRIGHTORDER',
    merchantFamily: 'BRIGHTORDER',
    category: 'Software / SaaS',
    confidence: 0.93,
    keywords: ['BRIGHTORDER'],
    reason: 'Matched fleet maintenance and workshop software vendor.',
  },
  {
    canonicalName: 'BORDER CONNECT',
    merchantFamily: 'BORDER CONNECT',
    category: 'Software / SaaS',
    confidence: 0.88,
    keywords: ['BORDER CONNECT'],
    reason: 'Matched cross-border logistics software vendor.',
  },
  {
    canonicalName: 'BIS SAFETY SOFTWARE',
    merchantFamily: 'BIS SAFETY',
    category: 'Training / Safety',
    confidence: 0.95,
    keywords: ['BIS SAFETY'],
    reason: 'Matched safety and training platform vendor.',
  },
  {
    canonicalName: 'ST. JOHN AMBULANCE',
    merchantFamily: 'ST. JOHN AMBULANCE',
    category: 'Training / Safety',
    confidence: 0.95,
    keywords: ['ST. JOHN AMBULANCE'],
    reason: 'Matched first-aid and training organization.',
  },
  {
    canonicalName: 'TELUS',
    merchantFamily: 'TELUS',
    category: 'Telecom / Connectivity',
    confidence: 0.96,
    keywords: ['TELUS MOBILITY', 'TELUS ONLINE PAYMENT', 'TELUS'],
    reason: 'Matched telecom and mobile service provider.',
  },
  {
    canonicalName: 'SUNCO COMMUNICATIONS',
    merchantFamily: 'SUNCO COMMUNICATIONS',
    category: 'Telecom / Connectivity',
    confidence: 0.86,
    keywords: ['SUNCO COMMUNICATION'],
    reason: 'Matched communications hardware or connectivity supplier.',
  },
  {
    canonicalName: 'LINDE CANADA',
    merchantFamily: 'LINDE',
    category: 'Transportation / Fleet / Operations',
    confidence: 0.9,
    keywords: ['LINDE CANADA', 'LINDE PKG'],
    reason: 'Matched industrial gas and operations supplier.',
  },
  {
    canonicalName: 'BEST BUY',
    merchantFamily: 'BEST BUY',
    category: 'Office Supplies',
    confidence: 0.86,
    keywords: ['BEST BUY'],
    reason: 'Matched electronics and office equipment retailer.',
  },
  {
    canonicalName: 'WALMART',
    merchantFamily: 'WALMART',
    category: 'Office Supplies',
    confidence: 0.82,
    keywords: ['WAL-MART', 'WALMART'],
    reason: 'Matched general retail procurement merchant.',
  },
  {
    canonicalName: 'TRACTOR SUPPLY',
    merchantFamily: 'TRACTOR SUPPLY',
    category: 'Transportation / Fleet / Operations',
    confidence: 0.84,
    keywords: ['TRACTOR SUPPLY'],
    reason: 'Matched fleet, equipment, and yard supply retailer.',
  },
  {
    canonicalName: 'ORKIN CANADA',
    merchantFamily: 'ORKIN',
    category: 'Facilities / Site Services',
    confidence: 0.92,
    keywords: ['ORKIN'],
    reason: 'Matched pest control and facilities service provider.',
  },
  {
    canonicalName: 'FLAIR AIRLINES',
    merchantFamily: 'FLAIR',
    category: 'Air Travel',
    confidence: 0.94,
    keywords: ['FLAIR DIR'],
    reason: 'Matched airline direct booking merchant.',
  },
  {
    canonicalName: 'PRICELINE',
    merchantFamily: 'PRICELINE',
    category: 'Lodging',
    confidence: 0.9,
    keywords: ['PRICELN', 'PRICELINE'],
    reason: 'Matched travel booking merchant tied to lodging charges.',
  },
  {
    canonicalName: 'AUDIBLE',
    merchantFamily: 'AUDIBLE',
    category: 'Software / SaaS',
    confidence: 0.8,
    keywords: ['AUDIBLE'],
    reason: 'Matched digital subscription merchant.',
  },
  {
    canonicalName: 'COBS BREAD',
    merchantFamily: 'COBS BREAD',
    category: 'Meals / Entertainment',
    confidence: 0.84,
    keywords: ['COBS BREAD'],
    reason: 'Matched bakery and food merchant.',
  },
  {
    canonicalName: 'TRAVEL INSURANCE',
    merchantFamily: 'TRAVEL SERVICES',
    category: 'Air Travel',
    confidence: 0.8,
    keywords: ['TRAVEL INS', 'ASSUR VOY'],
    reason: 'Matched travel-insurance or related travel service merchant.',
  },
  {
    canonicalName: 'BOSCH HYDRAULIC',
    merchantFamily: 'BOSCH HYDRAULIC',
    category: 'Transportation / Fleet / Operations',
    confidence: 0.82,
    keywords: ['HYDRAULIC', 'LUMBER'],
    reason: 'Matched industrial parts or yard supply wording.',
  },
  {
    canonicalName: 'TRUCK WASH / DETAILING',
    merchantFamily: 'TRUCK WASH / DETAILING',
    category: 'Vehicle Maintenance',
    confidence: 0.8,
    keywords: ['WWIT', 'MOBILE CAR', 'TRUCK WASH', 'CAR WASH'],
    reason: 'Matched truck wash or detailing service wording.',
  },
  {
    canonicalName: 'YARD / STORAGE SERVICES',
    merchantFamily: 'YARD / STORAGE',
    category: 'Transportation / Fleet / Operations',
    confidence: 0.78,
    keywords: ['YARD - SERV', 'STORAGE', 'TOTAL MARINE TRANS'],
    reason: 'Matched yard, storage, or fleet holding service wording.',
  },
]

function searchableMerchantText(transaction: Pick<NormalizedCsvTransaction, 'normalizedMerchantName' | 'merchantName' | 'description'>) {
  return [
    transaction.normalizedMerchantName,
    transaction.merchantName?.toUpperCase(),
    transaction.description?.toUpperCase(),
  ]
    .filter(Boolean)
    .join(' ')
}

export function findMerchantDictionaryMatch(
  transaction: Pick<NormalizedCsvTransaction, 'normalizedMerchantName' | 'merchantName' | 'description'>,
): MerchantDictionaryMatch | null {
  const normalizedMerchantName = transaction.normalizedMerchantName?.trim().toUpperCase()
  const searchable = searchableMerchantText(transaction)

  for (const rule of merchantDictionaryRules) {
    const exactMatched = normalizedMerchantName
      ? rule.exactNormalizedNames?.includes(normalizedMerchantName) ?? false
      : false
    const keywordMatched = rule.keywords?.some((keyword) => searchable.includes(keyword)) ?? false

    if (exactMatched || keywordMatched) {
      return {
        canonicalName: rule.canonicalName,
        merchantFamily: rule.merchantFamily,
        category: rule.category,
        confidence: rule.confidence,
        reason: rule.reason,
      }
    }
  }

  return null
}
