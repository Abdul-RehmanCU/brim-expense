import { describe, expect, it } from 'vitest'

import {
  parseInsightBriefPreview,
  parseInsightCsvPreview,
  parseInsightMermaidPreview,
} from '@/lib/insights/artifactPreview'
import {
  buildInsightBriefMarkdown,
  buildInsightCsv,
  buildInsightMermaid,
} from '@/lib/insights/artifacts'
import type { InsightQueryResponse } from '@/lib/api/backendClient'

const sampleResult: InsightQueryResponse = {
  question: 'Show top merchants by spend.',
  session_id: 'session-1',
  plan: {
    intent: 'top_merchants',
    mode: 'table',
    tool: 'spend.topMerchants',
    filters: { department: 'Marketing' },
    group_by: ['merchant_name'],
    metrics: ['sum_amount_cad', 'transaction_count'],
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
  summary: 'Top merchant is TOOT\'N TOTUM 100 -.',
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
      label: 'Delta',
      values: {
        sum_amount_cad: 5100,
        transaction_count: 4,
      },
    },
  ],
  citations: [
    {
      clause_id: 'clause-1',
      rule_code: 'RECEIPTS',
      title: 'Receipts',
      text: 'Receipts are required for reimbursement.',
      source: 'policy.pdf',
      match_score: 0.95,
    },
  ],
  visualization: 'table',
  metadata: {
    returned_count: 2,
  },
}

describe('artifact preview parsers', () => {
  it('parses CSV previews into columns and rows', () => {
    const preview = parseInsightCsvPreview(buildInsightCsv(sampleResult))

    expect(preview).not.toBeNull()
    expect(preview?.columns).toEqual(['label', 'sum_amount_cad', 'transaction_count'])
    expect(preview?.rows[0]).toEqual(["TOOT'N TOTUM 100 -", '13594.40', '13'])
  })

  it('parses Mermaid previews into ordered visual nodes', () => {
    const preview = parseInsightMermaidPreview(buildInsightMermaid(sampleResult))

    expect(preview).not.toBeNull()
    expect(preview?.primaryNodes.map((node) => node.title)).toEqual(['Question', 'Validation', 'Tool', 'Intent', 'Answer'])
    expect(preview?.filtersNode?.body).toContain('department: Marketing')
    expect(preview?.rowNodes).toHaveLength(2)
  })

  it('parses brief markdown into fields and sections', () => {
    const preview = parseInsightBriefPreview(buildInsightBriefMarkdown(sampleResult))

    expect(preview).not.toBeNull()
    expect(preview?.title).toBe('top_merchants')
    expect(preview?.fields.map((field) => field.label)).toEqual(['Question', 'Summary'])
    expect(preview?.sections.map((section) => section.heading)).toEqual(['Execution', 'Result Preview', 'Citations'])
    expect(preview?.sections[1]?.table?.rows[0]?.[0]).toBe("TOOT'N TOTUM 100 -")
  })
})
