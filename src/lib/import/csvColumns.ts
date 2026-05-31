export const requiredCsvColumns = [
  'Transaction Code',
  'Transaction Description',
  'Transaction Category',
  'Posting date of transaction',
  'Transaction Date',
  'Merchant Info DBA Name',
  'Transaction Amount',
  'Debit or Credit',
  'Merchant Category Code',
  'Merchant City',
  'Merchant Country',
  'Merchant Postal Code',
  'Merchant State/Province',
  'Conversion Rate',
] as const

export type RequiredCsvColumn = (typeof requiredCsvColumns)[number]
export type TransactionCsvRow = Record<RequiredCsvColumn, string>

export function findMissingColumns(headers: string[]) {
  const headerSet = new Set(headers.map((header) => header.trim()))

  return requiredCsvColumns.filter((column) => !headerSet.has(column))
}
