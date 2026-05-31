// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AssistantProvider } from '@/lib/assistant/AssistantProvider'
import { TalkToDataPage } from '@/pages/TalkToDataPage'

const apiMocks = vi.hoisted(() => ({
  createInsightSession: vi.fn(),
  downloadInsightArtifactFile: vi.fn(),
  getInsightSession: vi.fn(),
  generateInsightArtifactFile: vi.fn(),
  queryInsights: vi.fn(),
}))

vi.mock('@/components/layout/PageScaffold', () => ({
  PageScaffold: ({ children, title, description }: { children: ReactNode; title: string; description?: string }) => (
    <div>
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
      {children}
    </div>
  ),
}))

vi.mock('@/lib/ui/preferences', () => ({
  useUiPreferences: () => ({
    t: (key: string) => {
      if (key === 'talkToData.title') {
        return 'Talk to Data'
      }
      if (key === 'talkToData.eyebrow') {
        return 'Insights'
      }
      return key
    },
  }),
}))

vi.mock('@/lib/api/backendClient', () => apiMocks)

describe('TalkToDataPage', () => {
  beforeEach(() => {
    apiMocks.createInsightSession.mockReset()
    apiMocks.downloadInsightArtifactFile.mockReset()
    apiMocks.getInsightSession.mockReset()
    apiMocks.generateInsightArtifactFile.mockReset()
    apiMocks.queryInsights.mockReset()
    window.localStorage.clear()
  })

  it('creates a session, persists it, and renders citations for a response', async () => {
    apiMocks.createInsightSession.mockResolvedValue({
      session: {
        id: 'session-1',
        title: 'What does policy say about alcohol?',
        created_by_employee_id: null,
        created_at: '2026-05-31T00:00:00Z',
        updated_at: '2026-05-31T00:00:00Z',
      },
      messages: [],
    })
    apiMocks.queryInsights.mockResolvedValue({
      question: 'What does policy say about alcohol?',
      session_id: 'session-1',
      plan: {
        intent: 'policy_clause_lookup',
        mode: 'answer',
        tool: 'policy.retrieveClauses',
        filters: {},
        group_by: [],
        metrics: [],
        sort: [],
        limit: 5,
        visualization: 'table',
        comparison_options: {},
        report_options: {},
      },
      validation: {
        valid: true,
        errors: [],
        warnings: [],
      },
      planner_source: 'anthropic_structured',
      summary: 'Retrieved 1 policy clause match.',
      columns: ['label', 'text', 'match_score'],
      rows: [
        {
          label: 'Alcohol',
          values: {
            text: 'Alcohol requires manager approval.',
            match_score: 0.91,
          },
        },
      ],
      citations: [
        {
          rule_code: 'ALCOHOL',
          clause_id: 'clause-1',
          title: 'Alcohol',
          text: 'Alcohol requires manager approval.',
          source: 'policy-doc',
          match_score: 0.91,
        },
      ],
      visualization: 'table',
      metadata: {
        returned_count: 1,
      },
    })

    renderWithAssistant(<TalkToDataPage />)

    fireEvent.change(screen.getByPlaceholderText('Ask about spend, policy, or risk...'), {
      target: { value: 'What does policy say about alcohol?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(apiMocks.createInsightSession).toHaveBeenCalledTimes(1))
    expect(apiMocks.createInsightSession).toHaveBeenCalledWith({
      initial_question: 'What does policy say about alcohol?',
      page_context: {
        page: 'Talk to Data',
        route: 'talkToData',
        payload: {
          route_id: 'talkToData',
          summary: 'Ask finance questions over spend, policy, and risk data. The shared assistant carries context between pages.',
          filters: {},
          focus: null,
          metrics: {},
          focus_entities: [],
          visible_entities: [],
          artifacts: [],
          available_views: ['conversation', 'result preview', 'artifacts'],
          suggestions: [],
        },
      },
    })
    expect(apiMocks.queryInsights).toHaveBeenCalledWith({
      page_context: {
        page: 'Talk to Data',
        route: 'talkToData',
        payload: {
          route_id: 'talkToData',
          summary: 'Ask finance questions over spend, policy, and risk data. The shared assistant carries context between pages.',
          filters: {},
          focus: null,
          metrics: {},
          focus_entities: [],
          visible_entities: [],
          artifacts: [],
          available_views: ['conversation', 'result preview', 'artifacts'],
          suggestions: [],
        },
      },
      question: 'What does policy say about alcohol?',
      session_id: 'session-1',
    })

    expect((await screen.findAllByText('Retrieved 1 policy clause match.')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Citations').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Alcohol').length).toBeGreaterThan(0)
    expect(window.localStorage.getItem('brim-talk-to-data-session-id')).toBe('session-1')
  })

  it('restores a saved session and renders the previous assistant answer', async () => {
    window.localStorage.setItem('brim-talk-to-data-session-id', 'session-2')
    apiMocks.getInsightSession.mockResolvedValue({
      session: {
        id: 'session-2',
        title: 'Marketing spend',
        created_by_employee_id: null,
        created_at: '2026-05-31T00:00:00Z',
        updated_at: '2026-05-31T00:05:00Z',
      },
      messages: [
        {
          id: 'msg-user',
          session_id: 'session-2',
          role: 'user',
          content: 'What did Marketing spend by category?',
          metadata: {},
          created_at: '2026-05-31T00:00:00Z',
        },
        {
          id: 'msg-assistant',
          session_id: 'session-2',
          role: 'assistant',
          content: 'Top group is Travel. Total matching spend is CAD 1,200.00 across 3 transaction(s).',
          metadata: {
            kind: 'insight_response',
            question: 'What did Marketing spend by category?',
            session_id: 'session-2',
            plan: {
              intent: 'marketing_spend_by_category',
              mode: 'chart',
              tool: 'spend.groupBy',
              filters: { department: 'Marketing' },
              group_by: ['business_category'],
              metrics: ['sum_amount_cad', 'transaction_count'],
              sort: [],
              limit: 100,
              visualization: 'bar',
              comparison_options: {},
              report_options: {},
            },
            validation: {
              valid: true,
              errors: [],
              warnings: [],
            },
            planner_source: 'deterministic_followup',
            columns: ['label', 'sum_amount_cad', 'transaction_count'],
            rows: [
              {
                label: 'Travel',
                values: {
                  sum_amount_cad: 1200,
                  transaction_count: 3,
                },
              },
            ],
            citations: [],
            visualization: 'bar',
            metadata: {
              returned_count: 1,
            },
          },
          created_at: '2026-05-31T00:01:00Z',
        },
      ],
    })

    renderWithAssistant(<TalkToDataPage />)

    await waitFor(() => expect(apiMocks.getInsightSession).toHaveBeenCalledWith('session-2'))
    expect(
      (
        await screen.findAllByText('Top group is Travel. Total matching spend is CAD 1,200.00 across 3 transaction(s).')
      ).length,
    ).toBeGreaterThan(0)
    expect(screen.getByText(/Active session-/i)).toBeTruthy()
  })
})

function renderWithAssistant(node: ReactNode) {
  return render(<AssistantProvider>{node}</AssistantProvider>)
}
