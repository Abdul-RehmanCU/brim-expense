import { describe, expect, it } from 'vitest'

import type { InsightQueryResponse } from '@/lib/api/backendClient'
import { buildInsightPreviewChartSpec } from '@/lib/insights/resultPreview'

describe('buildInsightPreviewChartSpec', () => {
  it('aggregates department-vs-department comparisons into a usable bar chart', () => {
    const result: InsightQueryResponse = {
      question: 'Compare Engineering vs Marketing',
      session_id: 'session-1',
      plan: {
        intent: 'department_spend_comparison',
        mode: 'chart',
        tool: 'spend.compare',
        filters: { department: ['Marketing', 'Engineering'] },
        group_by: ['department'],
        metrics: ['sum_amount_cad', 'transaction_count', 'avg_amount_cad'],
        sort: [],
        limit: 100,
        visualization: 'bar',
        comparison_options: {
          dimension: 'department',
          targets: ['Marketing', 'Engineering'],
          focus_dimension: 'department',
        },
        report_options: {},
      },
      validation: { valid: true, errors: [], warnings: [] },
      planner_source: 'deterministic',
      summary: '',
      columns: [
        'label',
        'marketing_sum_amount_cad',
        'engineering_sum_amount_cad',
      ],
      rows: [
        {
          label: 'Engineering',
          values: {
            marketing_sum_amount_cad: 0,
            engineering_sum_amount_cad: 406114.26,
          },
        },
        {
          label: 'Marketing',
          values: {
            marketing_sum_amount_cad: 282819.61,
            engineering_sum_amount_cad: 0,
          },
        },
      ],
      citations: [],
      visualization: 'bar',
      metadata: {},
    }

    const spec = buildInsightPreviewChartSpec(result)

    expect(spec?.kind).toBe('bar')
    expect(spec && 'data' in spec ? spec.data : []).toEqual([
      { label: 'Marketing', value: 282819.61 },
      { label: 'Engineering', value: 406114.26 },
    ])
  })

  it('renders monthly grouped results as a line chart', () => {
    const result: InsightQueryResponse = {
      question: 'How much did Marketing spend last quarter? Show me a chart',
      session_id: 'session-1',
      plan: {
        intent: 'department_spend_trend',
        mode: 'chart',
        tool: 'spend.groupBy',
        filters: { department: 'Marketing', date_start: '2026-01-01', date_end: '2026-03-31' },
        group_by: ['month'],
        metrics: ['sum_amount_cad', 'transaction_count'],
        sort: [],
        limit: 24,
        visualization: 'line',
        comparison_options: {},
        report_options: {},
      },
      validation: { valid: true, errors: [], warnings: [] },
      planner_source: 'deterministic',
      summary: '',
      columns: ['label', 'sum_amount_cad'],
      rows: [
        { label: '2026-01', values: { sum_amount_cad: 1000 } },
        { label: '2026-02', values: { sum_amount_cad: 1800 } },
        { label: '2026-03', values: { sum_amount_cad: 900 } },
      ],
      citations: [],
      visualization: 'line',
      metadata: {},
    }

    const spec = buildInsightPreviewChartSpec(result)

    expect(spec?.kind).toBe('line')
    expect(spec && 'series' in spec ? spec.series[0].key : null).toBe('sum_amount_cad')
  })

  it('prefers a chart preview over metric cards when a single-row result is chart-intended', () => {
    const result: InsightQueryResponse = {
      question: 'Generate me some charts',
      session_id: 'session-1',
      plan: {
        intent: 'department_spend_trend',
        mode: 'chart',
        tool: 'spend.groupBy',
        filters: { department: 'Marketing' },
        group_by: ['month'],
        metrics: ['sum_amount_cad', 'transaction_count'],
        sort: [],
        limit: 24,
        visualization: 'bar',
        comparison_options: {},
        report_options: {},
      },
      validation: { valid: true, errors: [], warnings: [] },
      planner_source: 'deterministic_followup',
      summary: '',
      columns: ['label', 'sum_amount_cad'],
      rows: [{ label: '2026-01', values: { sum_amount_cad: 102773.43 } }],
      citations: [],
      visualization: 'bar',
      metadata: {},
    }

    const spec = buildInsightPreviewChartSpec(result)

    expect(spec?.kind).toBe('bar')
    expect(spec && 'data' in spec ? spec.data : []).toEqual([{ label: '2026-01', sum_amount_cad: 102773.43 }])
  })
})
