import { stableHash } from '@/lib/utils/hash'

export type SyntheticAssignmentEmployee = {
  id: string
  departmentId: string
  fullName: string
  email: string
  departmentName: string
}

export type SyntheticAssignmentInput = {
  merchant: string | null
  transactionDate: string | null
  amountCad: number
  sourceRowNumber: number
  transactionType?: string | null
  businessCategory?: string | null
}

export function assignSyntheticEmployee(
  input: SyntheticAssignmentInput,
  employees: SyntheticAssignmentEmployee[],
) {
  if (employees.length === 0) {
    return null
  }

  const heroEmployee = employees.find(
    (employee) => employee.fullName === 'Sarah Chen' && employee.departmentName === 'Marketing',
  )
  const assignmentKey = syntheticAssignmentKey(input)
  const heroScenario =
    heroEmployee &&
    stableHash(assignmentKey) % 37 === 0 &&
    input.amountCad >= 50 &&
    input.amountCad <= 1500

  if (heroScenario) {
    return heroEmployee
  }

  const employeeIndex = stableHash(assignmentKey) % employees.length

  return employees[employeeIndex]
}

function syntheticAssignmentKey(input: SyntheticAssignmentInput) {
  const merchant = (input.merchant ?? '').trim().toUpperCase()
  const transactionDate = input.transactionDate ?? ''
  const transactionType = (input.transactionType ?? '').trim().toLowerCase()
  const category = (input.businessCategory ?? '').trim().toLowerCase()

  if (
    transactionType.startsWith('cash_advance') ||
    category === 'cash advance / atm withdrawal' ||
    category === 'cash advance fee'
  ) {
    return `cash-event|${merchant}|${transactionDate}`
  }

  if (merchant && transactionDate) {
    return `merchant-date-amount|${merchant}|${transactionDate}|${input.amountCad.toFixed(2)}`
  }

  return `source-row|${merchant}|${transactionDate}|${input.amountCad.toFixed(2)}|${input.sourceRowNumber}`
}
