import { BarChart3, BookText } from 'lucide-react'
import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { InsightCitation, InsightQueryResponse } from '@/lib/api/backendClient'
import {
  buildInsightPreviewChartSpec,
  formatColumn,
  formatInsightValue,
  inferInsightColumns,
} from '@/lib/insights/resultPreview'

const chartPalette = ['#59c9a5', '#4b7bec', '#f59e0b', '#ef4444', '#8b5cf6']

export function TalkToDataResultTab({ result }: { result: InsightQueryResponse }) {
  const columns = useMemo(() => (result.columns.length > 0 ? result.columns : inferInsightColumns(result.rows)), [result])
  const chartSpec = useMemo(() => buildInsightPreviewChartSpec(result), [result])
  const groundingSources = useMemo(
    () => (Array.isArray(result.metadata.grounding_sources) ? result.metadata.grounding_sources.filter((value): value is string => typeof value === 'string') : []),
    [result.metadata.grounding_sources],
  )
  const artifactCapabilities = useMemo(
    () => (Array.isArray(result.metadata.artifact_capabilities) ? result.metadata.artifact_capabilities.filter((value): value is string => typeof value === 'string') : []),
    [result.metadata.artifact_capabilities],
  )
  const referencedEntityCount = useMemo(
    () => (Array.isArray(result.metadata.referenced_entities) ? result.metadata.referenced_entities.length : 0),
    [result.metadata.referenced_entities],
  )

  if (result.rows.length === 0) {
    return <p className="p-6 text-sm text-muted-foreground">No rows returned for this question.</p>
  }

  return (
    <div className="space-y-5 p-6">
      <section className="rounded-3xl border border-border/70 bg-background/60 p-5">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-base font-semibold text-foreground">
                <BarChart3 className="size-4 text-primary" aria-hidden="true" />
                Result preview
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                A quick visual read of the selected answer before you dig into the rows below.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <span className="status-chip bg-muted text-muted-foreground">{result.validation.valid ? 'Valid' : 'Blocked'}</span>
              <span className="status-chip bg-muted text-muted-foreground">{result.rows.length} rows</span>
              <span className="status-chip bg-muted text-muted-foreground">{result.citations.length} citations</span>
              {referencedEntityCount > 0 ? <span className="status-chip bg-muted text-muted-foreground">{referencedEntityCount} entities</span> : null}
            </div>
          </div>

          {groundingSources.length > 0 || artifactCapabilities.length > 0 ? (
            <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Grounded by</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {groundingSources.map((source) => (
                  <span key={source} className="status-chip bg-muted text-muted-foreground">
                    {source.replaceAll('_', ' ')}
                  </span>
                ))}
              </div>
              {artifactCapabilities.length > 0 ? (
                <>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Exports</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {artifactCapabilities.map((capability) => (
                      <span key={capability} className="status-chip bg-muted text-muted-foreground">
                        {capability}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-2xl bg-muted/35 p-4">
            <div className="mb-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span className="status-chip bg-background/80 text-muted-foreground">{chartSpec?.kind === 'metric' ? 'Metric readout' : 'Interactive chart preview'}</span>
              {chartSpec && chartSpec.kind !== 'metric' ? <span className="status-chip bg-background/80 text-muted-foreground">{chartSpec.series.length} series</span> : null}
            </div>
            <InsightChartPreview chartSpec={chartSpec} />
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-3xl border border-border/70 bg-background/60">
        <div className="border-b border-border/70 px-5 py-4">
          <p className="text-sm font-semibold text-foreground">Result rows</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">Review the exact rows behind the answer in a scrollable container.</p>
        </div>

        <div className="max-h-[36rem] overflow-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead className="table-head">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-5 py-4 font-medium">
                    {formatColumn(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/70">
              {result.rows.map((row) => (
                <tr key={row.label} className="table-row">
                  {columns.map((column) => (
                    <td key={`${row.label}-${column}`} className="px-5 py-4 text-muted-foreground">
                      {formatInsightValue(column === 'label' ? row.label : row.values[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {result.citations.length > 0 ? (
        <section className="rounded-3xl border border-border/70 bg-background/60 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <BookText className="size-4 text-primary" aria-hidden="true" />
            Grounding
          </div>
          <div className="mt-4 grid gap-3">
            {result.citations.map((citation) => (
              <ResultCitationCard key={citation.clause_id ?? `${citation.rule_code}-${citation.text.slice(0, 24)}`} citation={citation} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

function InsightChartPreview({
  chartSpec,
}: {
  chartSpec: ReturnType<typeof buildInsightPreviewChartSpec>
}) {
  if (!chartSpec) {
    return <p className="text-sm text-muted-foreground">This result does not include enough numeric structure for a visual preview yet.</p>
  }

  if (chartSpec.kind === 'metric') {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {chartSpec.metrics.map((metric) => (
          <div key={metric.label} className="min-w-0 rounded-2xl border border-border/70 bg-background/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{metric.label}</p>
            <p className="mt-2 break-all text-lg leading-tight font-semibold tabular-nums text-foreground sm:text-xl">
              {formatInsightValue(metric.value, metric.label.includes('amount') ? 'currency' : 'number')}
            </p>
          </div>
        ))}
      </div>
    )
  }

  const formatter = chartSpec.valueFormatter === 'currency' ? currencyFormatter : numberFormatter

  if (chartSpec.kind === 'line') {
    return (
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartSpec.data} margin={{ top: 12, right: 12, bottom: 12, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148,163,184,0.22)" />
          <XAxis dataKey={chartSpec.xKey} tickLine={false} axisLine={false} fontSize={12} tickFormatter={truncateChartLabel} />
          <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={formatter} />
          <Tooltip content={<InsightTooltip formatter={chartSpec.valueFormatter} />} cursor={{ stroke: 'rgba(75,124,236,0.22)', strokeWidth: 1 }} />
          {chartSpec.series.length > 1 ? <Legend formatter={renderLegendLabel} /> : null}
          {chartSpec.series.map((series, index) => (
            <Line
              key={series.key}
              type="monotone"
              dataKey={series.key}
              name={series.label}
              stroke={chartPalette[index % chartPalette.length]}
              strokeWidth={2.5}
              dot={{ r: 3 }}
              activeDot={{ r: 5, strokeWidth: 0 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartSpec.data} margin={{ top: 12, right: 12, bottom: 12, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148,163,184,0.22)" />
        <XAxis
          dataKey={chartSpec.xKey}
          tickLine={false}
          axisLine={false}
          fontSize={12}
          interval={0}
          angle={-18}
          textAnchor="end"
          height={52}
          tickFormatter={truncateChartLabel}
        />
        <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={formatter} />
        <Tooltip content={<InsightTooltip formatter={chartSpec.valueFormatter} />} cursor={{ fill: 'rgba(75,124,236,0.08)' }} />
        {chartSpec.series.length > 1 ? <Legend formatter={renderLegendLabel} /> : null}
        {chartSpec.series.map((series, index) => (
          <Bar key={series.key} dataKey={series.key} name={series.label} fill={chartPalette[index % chartPalette.length]} radius={[8, 8, 0, 0]} activeBar={{ fill: chartPalette[index % chartPalette.length] }} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

function InsightTooltip({
  active,
  formatter,
  label,
  payload,
}: {
  active?: boolean
  formatter: 'currency' | 'number'
  label?: string
  payload?: Array<{ name?: string; value?: number }>
}) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="chart-tooltip">
      {label ? <p className="font-medium text-foreground">{label}</p> : null}
      {payload.map((entry) => (
        <div key={entry.name} className="chart-tooltip-row">
          <span className="chart-tooltip-label">
            <span className="chart-tooltip-swatch" style={{ backgroundColor: '#4b7bec' }} />
            {entry.name ?? 'Value'}
          </span>
          <span className="font-medium text-foreground">{formatInsightValue(Number(entry.value ?? 0), formatter)}</span>
        </div>
      ))}
    </div>
  )
}

function renderLegendLabel(value: string) {
  return <span className="text-xs text-muted-foreground">{value}</span>
}

function truncateChartLabel(value: string) {
  return value.length > 14 ? `${value.slice(0, 12)}...` : value
}

function ResultCitationCard({ citation }: { citation: InsightCitation }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4">
      <p className="text-sm font-medium text-foreground">{citation.title ?? citation.rule_code ?? 'Policy citation'}</p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{citation.text}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {citation.rule_code ? <span>Rule {citation.rule_code}</span> : null}
        {citation.source ? <span>Source {citation.source}</span> : null}
        {typeof citation.match_score === 'number' ? <span>Match {citation.match_score.toFixed(3)}</span> : null}
      </div>
    </div>
  )
}

function currencyFormatter(value: number) {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'CAD',
    notation: 'compact',
    maximumFractionDigits: 1,
  })
}

function numberFormatter(value: number) {
  return value.toLocaleString(undefined, {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  })
}
