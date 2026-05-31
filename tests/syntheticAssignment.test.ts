import { describe, expect, it } from 'vitest'

import { assignSyntheticEmployee, type SyntheticAssignmentEmployee } from '@/lib/synthetic/assignment'

const employees: SyntheticAssignmentEmployee[] = [
  {
    id: 'employee-1',
    departmentId: 'department-1',
    fullName: 'Sarah Chen',
    email: 'sarah.chen@brim-demo.example',
    departmentName: 'Marketing',
  },
  {
    id: 'employee-2',
    departmentId: 'department-2',
    fullName: 'Marcus Green',
    email: 'marcus.green@brim-demo.example',
    departmentName: 'Engineering',
  },
]

describe('synthetic assignment', () => {
  it('assigns the same transaction input to the same employee', () => {
    const input = {
      merchant: 'FEDEX',
      transactionDate: '2025-09-02',
      amountCad: 23.98,
      sourceRowNumber: 2,
    }

    expect(assignSyntheticEmployee(input, employees)).toEqual(assignSyntheticEmployee(input, employees))
  })

  it('keeps a stable Sarah Chen hero scenario', () => {
    expect(
      assignSyntheticEmployee(
        {
          merchant: 'SUPER 8 MOTELS',
          transactionDate: '2025-09-10',
          amountCad: 188.75,
          sourceRowNumber: 37,
        },
        employees,
      )?.fullName,
    ).toBe('Sarah Chen')
  })
})
