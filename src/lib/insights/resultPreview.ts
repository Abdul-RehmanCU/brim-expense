import type { InsightQueryResponse, InsightResultRow } from '@/lib/api/backendClient'

export type InsightPreviewSeries = {
  key: string
  label: string
}

export type InsightPreviewChartSpec =
  | {
      kind: 'metric'
      metrics: Array<{ label: string; value: number }>
    }
  | {
      kind: 'bar' | 'line'
      data: Array<Record<string, number | string>>
      series: InsightPreviewSeries[]
      xKey: 'label'
      valueFormatter: 'currency' | 'number'
    }

const PRIMARY_METRICS = ['sum_amount_cad', 'amount_cad', 'avg_amount_cad', 'transaction_count', 'policy_flag_count', 'risk_flag_count', 'risk_score'] as const

export function inferInsightColumns(rows: InsightResultRow[]) {
  const columns = ['label']
  for (const row of rows) {
    for (const key of Object.keys(row.values)) {
      if (!columns.includes(key)) {
        columns.push(key)
      }
    }
  }
  return columns
}

export function buildInsightPreviewChartSpec(result: InsightQueryResponse): InsightPreviewChartSpec | null {
  if (result.rows.length === 0) {
    return null
  }

  const comparisonSpec = buildComparisonChartSpec(result)
  if (comparisonSpec) {
    return comparisonSpec
  }

  const numericColumns = pickNumericColumns(result.rows)
  const primaryMetric = pickPrimaryMetric(numericColumns)
  if (!primaryMetric) {
    return null
  }

  if (result.rows.length === 1 && isChartPreferred(result)) {
    const row = result.rows[0]
    return {
      kind: result.visualization === 'line' ? 'line' : 'bar',
      data: [
        {
          label: row.label,
          [primaryMetric]: toNumber(row.values[primaryMetric]),
        },
      ],
      series: [{ key: primaryMetric, label: formatColumn(primaryMetric) }],
      xKey: 'label',
      valueFormatter: primaryMetric.includes('amount') ? 'currency' : 'number',
    }
  }

  if (result.rows.length === 1) {
    const row = result.rows[0]
    return {
      kind: 'metric',
      metrics: numericColumns.slice(0, 4).map((key) => ({
        label: formatColumn(key),
        value: toNumber(row.values[key]),
      })),
    }
  }

  const kind = result.visualization === 'line' || result.plan.group_by[0] === 'month' ? 'line' : 'bar'
  return {
    kind,
    data: result.rows.slice(0, 12).map((row) => ({
      label: row.label,
      [primaryMetric]: toNumber(row.values[primaryMetric]),
    })),
    series: [{ key: primaryMetric, label: formatColumn(primaryMetric) }],
    xKey: 'label',
    valueFormatter: primaryMetric.includes('amount') ? 'currency' : 'number',
  }
}

function isChartPreferred(result: InsightQueryResponse) {
  return result.plan.mode === 'chart' || result.visualization === 'bar' || result.visualization === 'line'
}

function buildComparisonChartSpec(result: InsightQueryResponse): InsightPreviewChartSpec | null {
  if (result.plan.tool !== 'spend.compare') {
    return null
  }

  const comparisonTargets = Array.isArray(result.plan.comparison_options.targets)
    ? result.plan.comparison_options.targets.map((target) => String(target))
    : []
  if (comparisonTargets.length === 0) {
    return null
  }

  const numericColumns = pickNumericColumns(result.rows)
  const comparisonMetric = pickComparisonMetric(numericColumns)
  if (!comparisonMetric) {
    return null
  }

  const series = comparisonTargets
    .map((target) => {
      const key = `${slugifyTarget(target)}_${comparisonMetric}`
      return numericColumns.includes(key) ? { key, label: target } : null
    })
    .filter((entry): entry is InsightPreviewSeries => Boolean(entry))

  if (series.length === 0) {
    return null
  }

  const focusDimension = String(result.plan.group_by[0] ?? result.plan.comparison_options.focus_dimension ?? '')
  const comparisonDimension = String(result.plan.comparison_options.dimension ?? '')
  if (focusDimension && focusDimension === comparisonDimension) {
    return {
      kind: result.visualization === 'line' ? 'line' : 'bar',
      data: series.map((entry) => ({
        label: entry.label,
        value: result.rows.reduce((total, row) => total + toNumber(row.values[entry.key]), 0),
      })),
      series: [{ key: 'value', label: formatColumn(comparisonMetric) }],
      xKey: 'label',
      valueFormatter: comparisonMetric.includes('amount') ? 'currency' : 'number',
    }
  }

  return {
    kind: result.visualization === 'line' ? 'line' : 'bar',
    data: result.rows.slice(0, 12).map((row) => {
      const chartRow: Record<string, string | number> = { label: row.label }
      for (const entry of series) {
        chartRow[entry.key] = toNumber(row.values[entry.key])
      }
      return chartRow
    }),
    series,
    xKey: 'label',
    valueFormatter: comparisonMetric.includes('amount') ? 'currency' : 'number',
  }
}

function pickComparisonMetric(columns: string[]) {
  return PRIMARY_METRICS.find((metric) => columns.some((column) => column.endsWith(`_${metric}`))) ?? null
}

function pickPrimaryMetric(columns: string[]) {
  return PRIMARY_METRICS.find((metric) => columns.includes(metric)) ?? columns[0] ?? null
}

function pickNumericColumns(rows: InsightResultRow[]) {
  const keys = new Set<string>()
  for (const row of rows) {
    for (const [key, value] of Object.entries(row.values)) {
      if (typeof value === 'number') {
        keys.add(key)
      }
    }
  }
  return [...keys]
}

export function formatColumn(column: string) {
  return column.replaceAll('_', ' ')
}

export function formatInsightValue(value: unknown, formatter: 'currency' | 'number' = 'number') {
  if (typeof value === 'number') {
    if (formatter === 'currency') {
      return value.toLocaleString(undefined, {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 2,
      })
    }
    return value.toLocaleString(undefined, {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
    })
  }
  if (typeof value === 'string' && value.trim()) {
    return value
  }
  if (value === null || value === undefined) {
    return '-'
  }
  return String(value)
}

export function toNumber(value: unknown) {
  return typeof value === 'number' ? value : Number(value) || 0
}

function slugifyTarget(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replaceAll('&', 'and')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}
