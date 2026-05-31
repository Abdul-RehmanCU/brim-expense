// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SessionRail } from '@/components/talk-to-data/SessionRail'

describe('SessionRail', () => {
  it('shows only four chats by default and reveals the rest on demand', () => {
    const sessions = Array.from({ length: 6 }, (_, index) => ({
      id: `session-${index + 1}`,
      title: `Session ${index + 1}`,
      created_by_employee_id: null,
      created_at: `2026-05-${String(index + 1).padStart(2, '0')}T00:00:00Z`,
      updated_at: `2026-05-${String(index + 1).padStart(2, '0')}T00:05:00Z`,
    }))

    render(
      <SessionRail
        sessions={sessions}
        activeSessionId="session-1"
        isLoading={false}
        onSelectSession={vi.fn()}
        onStartNewChat={vi.fn()}
      />,
    )

    expect(screen.getByText('Session 1')).toBeTruthy()
    expect(screen.getByText('Session 2')).toBeTruthy()
    expect(screen.getByText('Session 3')).toBeTruthy()
    expect(screen.getByText('Session 4')).toBeTruthy()
    expect(screen.queryByText('Session 5')).toBeNull()
    expect(screen.queryByText('Session 6')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Show more/i }))

    expect(screen.getByText('Session 5')).toBeTruthy()
    expect(screen.getByText('Session 6')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Show less' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Show less' }))

    expect(screen.queryByText('Session 5')).toBeNull()
    expect(screen.queryByText('Session 6')).toBeNull()
  })
})
