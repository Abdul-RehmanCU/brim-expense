import { describe, expect, it } from 'vitest'

import { assignSyntheticEmployee, type SyntheticAssignmentEmployee } from '@/lib/synthetic/assignment'

const employees: SyntheticAssignmentEmployee[] = [
  {
    id: 'employee_1',
    departmentId: 'department_1',
    fullName: 'Sarah Chen',
    email: 'sarah@example.com',
    departmentName: 'Marketing',
  },
  {
    id: 'employee_2',
    departmentId: 'department_2',
    fullName: 'Jordan Lee',
    email: 'jordan@example.com',
    departmentName: 'Sales',
  },
  {
    id: 'employee_3',
    departmentId: 'department_3',
    fullName: 'Mateo Rivera',
    email: 'mateo@example.com',
    departmentName: 'Customer Success',
  },
]

describe('synthetic employee assignment', () => {
  it('keeps exact duplicate merchant/date/amount rows on the same synthetic cardholder', () => {
    const first = assignSyntheticEmployee(
      {
        merchant: 'ROSENBERG TR-LI',
        transactionDate: '2026-01-08',
        amountCad: 413.53,
        sourceRowNumber: 101,
        businessCategory: 'Cash Advance / ATM Withdrawal',
        transactionType: 'cash_advance',
      },
      employees,
    )
    const second = assignSyntheticEmployee(
      {
        merchant: 'ROSENBERG TR-LI',
        transactionDate: '2026-01-08',
        amountCad: 413.53,
        sourceRowNumber: 102,
        businessCategory: 'Cash Advance / ATM Withdrawal',
        transactionType: 'cash_advance',
      },
      employees,
    )

    expect(second?.id).toBe(first?.id)
  })

  it('keeps same-day cash advance event rows together even when amounts differ', () => {
    const first = assignSyntheticEmployee(
      {
        merchant: 'ROSENBERG TR-LI',
        transactionDate: '2026-01-08',
        amountCad: 413.53,
        sourceRowNumber: 101,
        businessCategory: 'Cash Advance / ATM Withdrawal',
        transactionType: 'cash_advance',
      },
      employees,
    )
    const second = assignSyntheticEmployee(
      {
        merchant: 'ROSENBERG TR-LI',
        transactionDate: '2026-01-08',
        amountCad: 109.47,
        sourceRowNumber: 103,
        businessCategory: 'Cash Advance / ATM Withdrawal',
        transactionType: 'cash_advance',
      },
      employees,
    )

    expect(second?.id).toBe(first?.id)
  })
})
