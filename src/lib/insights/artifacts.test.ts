import { describe, expect, it } from 'vitest'

import type { InsightQueryResponse } from '@/lib/api/backendClient'
import {
  buildInsightArtifactFileName,
  buildInsightBriefMarkdown,
  buildInsightCsv,
  buildInsightMermaid,
  copyArtifactText,
} from '@/lib/insights/artifacts'

const sampleResult: InsightQueryResponse = {
  question: 'Can you show me the merchants just for Marketing?',
  session_id: 'session-1',
  plan: {
    intent: 'top_merchants',
    mode: 'table',
    tool: 'spend.topMerchants',
    filters: { department: 'Marketing' },
    group_by: ['merchant'],
    metrics: ['sum_amount_cad', 'transaction_count'],
    sort: [{ field: 'sum_amount_cad', direction: 'desc' }],
    limit: 100,
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
  summary: "Top group is TOOT'N TOTUM 100 -.",
  columns: ['label', 'sum_amount_cad', 'transaction_count'],
  rows: [
    {
      label: "TOOT'N TOTUM 100 -",
      values: {
        sum_amount_cad: 13594.4,
        transaction_count: 13,
      },
    },
    {
      label: 'CENEX-FUOC OF CARPIO',
      values: {
        sum_amount_cad: 12258.58,
        transaction_count: 13,
      },
    },
  ],
  citations: [
    {
      rule_code: 'RECEIPT_REQUIRED',
      clause_id: 'clause-1',
      title: 'Receipts',
      text: 'Receipts are required for reimbursement.',
      source: 'policy-doc',
      match_score: 0.92,
    },
  ],
  visualization: 'table',
  metadata: {
    returned_count: 2,
  },
}

describe('insight artifacts', () => {
  it('builds csv output from insight rows', () => {
    const csv = buildInsightCsv(sampleResult)

    expect(csv).toContain('label,sum_amount_cad,transaction_count')
    expect(csv).toContain(`TOOT'N TOTUM 100 -,13594.40,13`)
  })

  it('builds mermaid diagram output from the plan and summary', () => {
    const diagram = buildInsightMermaid(sampleResult)

    expect(diagram).toContain('flowchart TD')
    expect(diagram).toContain('Tool<br/>spend.topMerchants')
    expect(diagram).toContain('Filters<br/>department: Marketing')
  })

  it('builds markdown briefing output with citations', () => {
    const brief = buildInsightBriefMarkdown(sampleResult)

    expect(brief).toContain('# top_merchants')
    expect(brief).toContain('## Result Preview')
    expect(brief).toContain('## Citations')
    expect(brief).toContain('Receipts are required for reimbursement.')
  })

  it('builds artifact file names by type', () => {
    expect(buildInsightArtifactFileName(sampleResult, 'csv')).toBe('top-merchants.csv')
    expect(buildInsightArtifactFileName(sampleResult, 'diagram')).toBe('top-merchants.mmd')
    expect(buildInsightArtifactFileName(sampleResult, 'brief')).toBe('top-merchants.md')
  })

  it('falls back to execCommand when clipboard writes reject', async () => {
    const originalClipboard = navigator.clipboard
    const originalDocument = globalThis.document
    const writeText = async () => {
      throw new Error('Clipboard unavailable')
    }
    const mockTextArea = {
      value: '',
      style: {},
      focus: () => undefined,
      select: () => undefined,
    }
    const mockDocument = {
      body: {
        appendChild: () => undefined,
        removeChild: () => undefined,
      },
      createElement: () => mockTextArea,
      execCommand: () => true,
    } as unknown as Document

    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: mockDocument,
    })

    try {
      await expect(copyArtifactText('diagram body')).resolves.toBeUndefined()
    } finally {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: originalClipboard,
      })
      Object.defineProperty(globalThis, 'document', {
        configurable: true,
        value: originalDocument,
      })
    }
  })
})
